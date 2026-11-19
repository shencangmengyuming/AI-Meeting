from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class FollowUpRequest:
    session_id: str
    request_id: str
    current_question_number: str
    current_question: str
    answer_content: str
    fallback_question: str | None
    current_follow_up_count: int
    max_follow_up: int


@dataclass(frozen=True)
class FollowUpQuestion:
    question_number: str
    question_content: str
    follow_up_count: int


class InterviewFollowUpAgent(Protocol):
    async def generate(self, request: FollowUpRequest) -> FollowUpQuestion | None: ...


@dataclass(frozen=True)
class FollowUpRuleContext:
    score: int | None
    missing_points: tuple[str, ...]
    follow_up_needed_from_ai: bool
    follow_up_question_hint: str | None
    follow_up_count: int
    max_follow_up: int
    interview_completed: bool
    low_score_threshold: int = 60


@dataclass(frozen=True)
class FollowUpRuleDecision:
    need_follow_up: bool
    reason_code: str
    reason_text: str
    resolved_max_follow_up: int
    chain_id: str = "default_followup_chain"
    rule_version: str = "v1.0.0"
    fallback: bool = False


class FollowUpRuleService:
    def __init__(
        self,
        *,
        default_max_follow_up: int = 2,
        default_low_score_threshold: int = 60,
    ) -> None:
        self.default_max_follow_up = max(default_max_follow_up, 1)
        self.default_low_score_threshold = max(default_low_score_threshold, 0)

    def decide(self, context: FollowUpRuleContext) -> FollowUpRuleDecision:
        resolved_max = (
            context.max_follow_up
            if context.max_follow_up > 0
            else self.default_max_follow_up
        )
        if context.interview_completed:
            return self._decision(
                False,
                "INTERVIEW_COMPLETED",
                "interview already completed",
                resolved_max,
            )
        if context.follow_up_count >= resolved_max:
            return self._decision(
                False,
                "FOLLOW_UP_LIMIT_REACHED",
                "follow-up limit reached",
                resolved_max,
            )
        if context.follow_up_needed_from_ai:
            return self._decision(
                True,
                "AI_SUGGESTED",
                "follow-up suggested by ai result",
                resolved_max,
            )

        threshold = (
            context.low_score_threshold
            if context.low_score_threshold >= 0
            else self.default_low_score_threshold
        )
        if context.score is not None and context.score < threshold:
            return self._decision(
                True,
                "LOW_SCORE",
                f"score below threshold: {context.score} < {threshold}",
                resolved_max,
            )
        if context.missing_points or _has_text(context.follow_up_question_hint):
            return self._decision(
                True,
                "MISSING_POINTS",
                "missing points or follow-up hint detected",
                resolved_max,
            )
        return self._decision(
            False,
            "NO_RULE_TRIGGER",
            "no follow-up trigger matched",
            resolved_max,
        )

    @staticmethod
    def _decision(
        need_follow_up: bool,
        reason_code: str,
        reason_text: str,
        resolved_max_follow_up: int,
    ) -> FollowUpRuleDecision:
        return FollowUpRuleDecision(
            need_follow_up=need_follow_up,
            reason_code=reason_code,
            reason_text=reason_text,
            resolved_max_follow_up=resolved_max_follow_up,
        )


def _has_text(value: str | None) -> bool:
    return bool(value and value.strip())
