from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Any, Mapping


class InterviewFlowStatus(StrEnum):
    INIT = "INIT"
    ASKING = "ASKING"
    EVALUATING = "EVALUATING"
    FOLLOW_UP = "FOLLOW_UP"
    COMPLETED = "COMPLETED"


LEGAL_TRANSITIONS: dict[InterviewFlowStatus, frozenset[InterviewFlowStatus]] = {
    InterviewFlowStatus.INIT: frozenset(
        {InterviewFlowStatus.ASKING, InterviewFlowStatus.COMPLETED}
    ),
    InterviewFlowStatus.ASKING: frozenset(
        {
            InterviewFlowStatus.EVALUATING,
            InterviewFlowStatus.FOLLOW_UP,
            InterviewFlowStatus.COMPLETED,
        }
    ),
    InterviewFlowStatus.EVALUATING: frozenset(
        {
            InterviewFlowStatus.ASKING,
            InterviewFlowStatus.FOLLOW_UP,
            InterviewFlowStatus.COMPLETED,
        }
    ),
    InterviewFlowStatus.FOLLOW_UP: frozenset(
        {
            InterviewFlowStatus.EVALUATING,
            InterviewFlowStatus.ASKING,
            InterviewFlowStatus.COMPLETED,
        }
    ),
    InterviewFlowStatus.COMPLETED: frozenset(),
}


@dataclass(frozen=True)
class InterviewFlowState:
    status: InterviewFlowStatus
    current_index: int
    current_question_number: str | None
    total_questions: int
    follow_up_count: int = 0
    max_follow_up: int = 2
    version: int = 1
    total_score: int = 0

    @property
    def finished(self) -> bool:
        return self.status is InterviewFlowStatus.COMPLETED

    @classmethod
    def initial(cls, total_questions: int) -> "InterviewFlowState":
        return cls(
            status=InterviewFlowStatus.ASKING,
            current_index=0,
            current_question_number="1",
            total_questions=total_questions,
        )

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "InterviewFlowState":
        question_number = _optional_text(value.get("currentQuestionNumber"))
        current_index = _integer(value.get("currentIndex"), -1)
        if current_index < 0:
            current_index = _index_from_question_number(question_number)
        status_value = str(value.get("status") or "ASKING").upper()
        if bool(value.get("finished")):
            status_value = "COMPLETED"
        return cls(
            status=InterviewFlowStatus(status_value),
            current_index=max(current_index, 0),
            current_question_number=question_number,
            total_questions=max(_integer(value.get("totalQuestions"), 0), 0),
            follow_up_count=max(_integer(value.get("followUpCount"), 0), 0),
            max_follow_up=max(_integer(value.get("maxFollowUp"), 2), 1),
            version=max(_integer(value.get("version"), 1), 1),
            total_score=max(_integer(value.get("totalScore"), 0), 0),
        )

    def to_mapping(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "currentIndex": self.current_index,
            "currentQuestionNumber": self.current_question_number,
            "totalQuestions": self.total_questions,
            "followUpCount": self.follow_up_count,
            "maxFollowUp": self.max_follow_up,
            "version": self.version,
            "totalScore": self.total_score,
            "finished": self.finished,
        }


class InterviewFlowStateMachine:
    def move_to_evaluating(self, state: InterviewFlowState) -> InterviewFlowState:
        return self._transition(state, InterviewFlowStatus.EVALUATING)

    def start_follow_up(
        self,
        state: InterviewFlowState,
        question_number: str,
    ) -> InterviewFlowState:
        normalized = question_number.strip()
        if not normalized:
            raise ValueError("follow-up question number is required")
        if (
            state.status is not InterviewFlowStatus.FOLLOW_UP
            and InterviewFlowStatus.FOLLOW_UP not in LEGAL_TRANSITIONS[state.status]
        ):
            raise self._illegal_transition(
                state.status, InterviewFlowStatus.FOLLOW_UP
            )
        return replace(
            state,
            status=InterviewFlowStatus.FOLLOW_UP,
            current_question_number=normalized,
            follow_up_count=state.follow_up_count + 1,
            version=state.version + 1,
        )

    def advance_main_question(
        self,
        state: InterviewFlowState,
    ) -> InterviewFlowState:
        if state.status not in {
            InterviewFlowStatus.ASKING,
            InterviewFlowStatus.EVALUATING,
            InterviewFlowStatus.FOLLOW_UP,
        }:
            raise self._illegal_transition(state.status, InterviewFlowStatus.ASKING)
        next_index = state.current_index + 1
        if state.total_questions <= 0 or next_index >= state.total_questions:
            return replace(
                state,
                status=InterviewFlowStatus.COMPLETED,
                current_question_number=None,
                follow_up_count=0,
                version=state.version + 1,
            )
        return replace(
            state,
            status=InterviewFlowStatus.ASKING,
            current_index=next_index,
            current_question_number=str(next_index + 1),
            follow_up_count=0,
            version=state.version + 1,
        )

    def mark_completed(self, state: InterviewFlowState) -> InterviewFlowState:
        if state.status is InterviewFlowStatus.COMPLETED:
            return state
        if InterviewFlowStatus.COMPLETED not in LEGAL_TRANSITIONS[state.status]:
            raise self._illegal_transition(
                state.status, InterviewFlowStatus.COMPLETED
            )
        return replace(
            state,
            status=InterviewFlowStatus.COMPLETED,
            current_question_number=None,
            follow_up_count=0,
            version=state.version + 1,
        )

    def _transition(
        self,
        state: InterviewFlowState,
        target: InterviewFlowStatus,
    ) -> InterviewFlowState:
        if state.status is target:
            return state
        if target not in LEGAL_TRANSITIONS[state.status]:
            raise self._illegal_transition(state.status, target)
        return replace(state, status=target, version=state.version + 1)

    @staticmethod
    def _illegal_transition(
        source: InterviewFlowStatus,
        target: InterviewFlowStatus,
    ) -> ValueError:
        return ValueError(f"illegal interview flow transition: {source} -> {target}")


def _index_from_question_number(question_number: str | None) -> int:
    if not question_number:
        return 0
    main_number = question_number.split("-F", 1)[0]
    try:
        return max(int(main_number) - 1, 0)
    except ValueError:
        return 0


def _integer(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None
