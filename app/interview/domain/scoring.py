from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ScoringRequest:
    session_id: str
    request_id: str
    question_number: str
    question_content: str
    answer_content: str


@dataclass(frozen=True)
class ScoringResult:
    score: int
    feedback: str = ""
    missing_points: tuple[str, ...] = ()
    follow_up_needed: bool = False
    follow_up_question: str | None = None

    def __post_init__(self) -> None:
        if not 0 <= self.score <= 100:
            raise ValueError("score must be between 0 and 100")

class InterviewScoringAgent(Protocol):
    async def evaluate(self, request: ScoringRequest) -> ScoringResult: ...
