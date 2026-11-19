from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class TranscriptionUpdate:
    full_text: str
    committed_text: str
    live_text: str
    revision: int
    final: bool
    display_text: str = ""
    segment_id: int = 0
    segment_text: str = ""
    pgs: str | None = None
    rg: tuple[int, int] | None = None
    bg: int | None = None
    ed: int | None = None


@dataclass
class _Segment:
    segment_id: int
    text: str
    finalized: bool = False
    bg: int | None = None
    ed: int | None = None


class AstTranscriptionAssembler:
    def __init__(self) -> None:
        self._segments: dict[int, _Segment] = {}
        self._revision = 0

    def apply(
        self,
        *,
        segment_id: int,
        text: str,
        finalized: bool,
        pgs: str | None = None,
        rg: tuple[int, int] | list[int] | None = None,
        bg: int | None = None,
        ed: int | None = None,
    ) -> TranscriptionUpdate:
        if pgs:
            self._apply_with_pgs(segment_id, pgs, rg, text, finalized)
        else:
            self._apply_without_pgs(segment_id, bg, ed, text, finalized)
        self._revision += 1
        ordered = list(self._ordered_segments())
        full_text = "".join(segment.text for segment in ordered)
        if finalized:
            committed = full_text
        else:
            committed = "".join(
                segment.text
                for segment in ordered
                if segment.segment_id < segment_id or segment.finalized
            )
        live = (
            ""
            if finalized
            else full_text[len(committed) :]
            if committed and full_text.startswith(committed)
            else text or full_text
        )
        return TranscriptionUpdate(
            full_text=full_text,
            committed_text=committed,
            live_text=live,
            revision=self._revision,
            final=finalized,
            display_text=full_text,
            segment_id=segment_id,
            segment_text=text,
            pgs=pgs,
            rg=(int(rg[0]), int(rg[1])) if rg and len(rg) >= 2 else None,
            bg=bg,
            ed=ed,
        )

    def _apply_with_pgs(
        self,
        segment_id: int,
        pgs: str,
        rg: tuple[int, int] | list[int] | None,
        text: str,
        finalized: bool,
    ) -> None:
        if pgs.lower() == "rpl" and rg and len(rg) >= 2:
            start, end = sorted((int(rg[0]), int(rg[1])))
            for candidate in range(start, end + 1):
                self._segments.pop(candidate, None)
        self._upsert(segment_id, text, finalized)

    def _apply_without_pgs(
        self,
        segment_id: int,
        bg: int | None,
        ed: int | None,
        text: str,
        finalized: bool,
    ) -> None:
        if bg is None or ed is None:
            existing = self._segments.get(segment_id)
            if existing and existing.finalized and _is_punctuation(text):
                existing.text = _append_punctuation(existing.text, text)
                return
            if existing and existing.finalized:
                return
            self._upsert(segment_id, text, finalized)
            return
        same_range = next(
            (
                segment
                for segment in self._segments.values()
                if segment.bg == bg and segment.ed == ed
            ),
            None,
        )
        if same_range and _is_punctuation(text) and same_range.text.strip():
            same_range.text = _append_punctuation(same_range.text, text)
            same_range.finalized = same_range.finalized or finalized
            return

        reusable = self._find_reusable(bg, ed, text)
        if reusable is not None:
            reusable.text = text
            reusable.finalized = reusable.finalized or finalized
            reusable.bg = bg
            reusable.ed = ed
            self._remove_covered(bg, ed, text, retained_id=reusable.segment_id)
            return

        self._remove_covered(bg, ed, text, retained_id=None)
        self._upsert(segment_id, text, finalized, bg=bg, ed=ed)

    def _find_reusable(self, bg: int, ed: int, text: str) -> _Segment | None:
        best: _Segment | None = None
        best_score = -1.0
        for segment in self._segments.values():
            if segment.bg is None or segment.ed is None:
                continue
            if segment.bg == bg and segment.ed == ed:
                return segment
            ratio = _overlap_ratio(bg, ed, segment.bg, segment.ed)
            if ratio < 0.6 or not _same_evolution(segment.text, text):
                continue
            score = ratio + (1.0 if _contains(text, segment.text) else 0.0)
            if score > best_score:
                best, best_score = segment, score
        return best

    def _remove_covered(
        self,
        bg: int,
        ed: int,
        text: str,
        *,
        retained_id: int | None,
    ) -> None:
        remove = [
            segment_id
            for segment_id, segment in self._segments.items()
            if segment_id != retained_id
            and segment.bg is not None
            and segment.ed is not None
            and bg <= segment.bg
            and ed >= segment.ed
            and _same_evolution(segment.text, text)
        ]
        for segment_id in remove:
            self._segments.pop(segment_id, None)

    def _upsert(
        self,
        segment_id: int,
        text: str,
        finalized: bool,
        *,
        bg: int | None = None,
        ed: int | None = None,
    ) -> None:
        segment = self._segments.get(segment_id)
        if segment is None:
            segment = _Segment(segment_id, text)
            self._segments[segment_id] = segment
        segment.text = text
        segment.finalized = segment.finalized or finalized
        if bg is not None:
            segment.bg = bg
        if ed is not None:
            segment.ed = ed

    def _ordered_segments(self) -> Iterable[_Segment]:
        return (self._segments[key] for key in sorted(self._segments))


def _overlap_ratio(bg1: int, ed1: int, bg2: int, ed2: int) -> float:
    overlap = min(ed1, ed2) - max(bg1, bg2)
    if overlap <= 0:
        return 0.0
    return overlap / min(max(1, ed1 - bg1), max(1, ed2 - bg2))


def _comparable(text: str | None) -> str:
    return "".join(character for character in (text or "") if character.isalnum())


def _same_evolution(existing: str, incoming: str) -> bool:
    left, right = _comparable(existing), _comparable(incoming)
    if not left or not right:
        return False
    if left == right or left in right or right in left:
        return True
    common = 0
    for left_character, right_character in zip(left, right):
        if left_character != right_character:
            break
        common += 1
    return common / min(len(left), len(right)) >= 0.8


def _contains(source: str, candidate: str) -> bool:
    left, right = _comparable(source), _comparable(candidate)
    return bool(left and right and right in left)


def _is_punctuation(value: str) -> bool:
    trimmed = value.rstrip()
    return bool(trimmed) and all(
        character.isspace() or not character.isalnum() for character in trimmed
    )


def _append_punctuation(base: str, punctuation: str) -> str:
    base, suffix = base.rstrip(), punctuation.rstrip()
    return base if not suffix or base.endswith(suffix) else base + suffix
