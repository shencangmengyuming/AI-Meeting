import json

import pytest

from app.core.errors import BusinessError
from app.interview.application.answers import InterviewAnswerService
from app.interview.domain.scoring import (
    InterviewScoringAgent,
    ScoringRequest,
    ScoringResult,
)


class Collection:
    def __init__(self, document: dict[str, object] | None = None) -> None:
        self.document = document
        self.inserted: list[dict[str, object]] = []

    async def find_one(self, *args: object, **kwargs: object):
        return self.document

    async def insert_one(self, document: dict[str, object]) -> None:
        self.inserted.append(document)


class SnapshotCollection(Collection):
    async def replace_one(
        self,
        query: dict[str, object],
        document: dict[str, object],
        *,
        upsert: bool,
    ):
        del query, upsert
        self.document = document
        return type("Result", (), {"matched_count": 0, "upserted_id": "new"})()


class Database:
    def __init__(self) -> None:
        self.collections = {
            "interview_session": Collection({"_id": "session"}),
            "interview_question": Collection(),
            "interview_turn": Collection(),
            "interview_runtime_snapshot": SnapshotCollection(),
        }

    def __getitem__(self, name: str) -> Collection:
        return self.collections[name]


class RedisStub:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.hashes = {
            "interview:questions:session:session-1": {
                "1": "First question",
                "2": "Second question",
            }
        }

    async def get(self, key: str):
        return self.values.get(key)

    async def set(
        self,
        key: str,
        value: str,
        *,
        nx: bool = False,
        ex: int | None = None,
    ):
        if nx and key in self.values:
            return False
        self.values[key] = value
        return True

    async def delete(self, key: str) -> int:
        return int(self.values.pop(key, None) is not None)

    async def hgetall(self, key: str):
        return self.hashes.get(key, {})

    async def hset(self, key: str, mapping: dict[str, str]):
        self.hashes[key] = mapping


class SuccessfulScorer(InterviewScoringAgent):
    async def evaluate(self, request: ScoringRequest) -> ScoringResult:
        assert request.question_content == "First question"
        return ScoringResult(
            score=80,
            feedback="Good answer",
            missing_points=("edge cases",),
            follow_up_needed=False,
            follow_up_question=None,
        )


class FailingScorer(InterviewScoringAgent):
    async def evaluate(self, request: ScoringRequest) -> ScoringResult:
        raise RuntimeError("provider unavailable")


class LowScoreScorer(InterviewScoringAgent):
    async def evaluate(self, request: ScoringRequest) -> ScoringResult:
        return ScoringResult(
            score=50,
            feedback="Needs more detail",
            follow_up_needed=True,
            follow_up_question="How would you handle retries?",
        )


class StrongFollowUpScorer(InterviewScoringAgent):
    async def evaluate(self, request: ScoringRequest) -> ScoringResult:
        assert request.question_number == "1-F1"
        return ScoringResult(score=90, feedback="Clarified")


class FollowUpAgentStub:
    def __init__(self) -> None:
        self.calls: list[object] = []

    async def generate(self, request: object):
        from app.interview.domain import follow_up

        self.calls.append(request)
        return follow_up.FollowUpQuestion(
            question_number="1-F1",
            question_content="How would you handle retries?",
            follow_up_count=1,
        )


class UnexpectedFollowUpAgent:
    async def generate(self, request: object):
        raise AssertionError("follow-up agent should not be called")


class UnexpectedScorer(InterviewScoringAgent):
    async def evaluate(self, request: ScoringRequest) -> ScoringResult:
        raise AssertionError("archived answer must not be scored again")


@pytest.mark.anyio
async def test_successful_scoring_is_committed_before_flow_advances() -> None:
    database = Database()
    redis = RedisStub()
    redis.values["interview:flow:session:session-1"] = json.dumps(
        {
            "status": "ASKING",
            "currentQuestionNumber": "1",
            "totalQuestions": 2,
            "totalScore": 0,
            "finished": False,
        }
    )
    service = InterviewAnswerService(database, redis, SuccessfulScorer())  # type: ignore[arg-type]

    response = await service.submit(
        "session-1", 42, "1", "My answer", "request-1"
    )

    flow = json.loads(redis.values["interview:flow:session:session-1"])
    turn = database.collections["interview_turn"].inserted[0]
    assert response["score"] == 80
    assert response["totalScore"] == 80
    assert response["feedback"] == "Good answer"
    assert response["missingPoints"] == ["edge cases"]
    assert response["followUpNeeded"] is False
    assert flow["currentQuestionNumber"] == "2"
    assert flow["totalScore"] == 80
    assert turn["score"] == 80


@pytest.mark.anyio
async def test_successful_answer_persists_runtime_snapshot_with_cas_version() -> None:
    database = Database()
    redis = RedisStub()
    redis.values["interview:flow:session:session-1"] = json.dumps(
        {
            "status": "ASKING",
            "currentQuestionNumber": "1",
            "totalQuestions": 2,
            "totalScore": 0,
            "finished": False,
        }
    )
    service = InterviewAnswerService(database, redis, SuccessfulScorer())  # type: ignore[arg-type]

    await service.submit("session-1", 42, "1", "My answer", "request-1")

    snapshot = database.collections["interview_runtime_snapshot"].document
    assert snapshot is not None
    assert snapshot["version"] == 1
    assert snapshot["mutationId"] == "request-1"


@pytest.mark.anyio
async def test_scoring_failure_does_not_advance_flow_or_write_turn() -> None:
    database = Database()
    redis = RedisStub()
    original_flow = {
        "status": "ASKING",
        "currentQuestionNumber": "1",
        "totalQuestions": 2,
        "totalScore": 0,
        "finished": False,
    }
    redis.values["interview:flow:session:session-1"] = json.dumps(original_flow)
    service = InterviewAnswerService(database, redis, FailingScorer())  # type: ignore[arg-type]

    with pytest.raises(BusinessError) as error:
        await service.submit("session-1", 42, "1", "My answer", "request-1")

    assert error.value.code == "B000001"
    assert json.loads(redis.values["interview:flow:session:session-1"]) == original_flow
    assert database.collections["interview_turn"].inserted == []


def test_scoring_result_rejects_score_outside_java_contract() -> None:
    with pytest.raises(ValueError, match="between 0 and 100"):
        ScoringResult(score=101)


@pytest.mark.anyio
async def test_low_score_starts_follow_up_without_advancing_main_question() -> None:
    database = Database()
    redis = RedisStub()
    redis.values["interview:flow:session:session-1"] = json.dumps(
        {
            "status": "ASKING",
            "currentIndex": 0,
            "currentQuestionNumber": "1",
            "totalQuestions": 2,
            "followUpCount": 0,
            "maxFollowUp": 2,
            "version": 1,
            "totalScore": 0,
            "finished": False,
        }
    )
    follow_up_agent = FollowUpAgentStub()
    service = InterviewAnswerService(
        database,  # type: ignore[arg-type]
        redis,  # type: ignore[arg-type]
        LowScoreScorer(),
        follow_up_agent=follow_up_agent,  # type: ignore[arg-type]
    )

    response = await service.submit(
        "session-1", 42, "1", "A partial answer", "request-follow-up"
    )

    flow = json.loads(redis.values["interview:flow:session:session-1"])
    assert response["nextQuestionNumber"] == "1-F1"
    assert response["nextQuestion"] == "How would you handle retries?"
    assert response["isFollowUp"] is True
    assert response["followUpCount"] == 1
    assert response["totalScore"] == 50
    assert flow["status"] == "FOLLOW_UP"
    assert flow["currentIndex"] == 0
    assert flow["currentQuestionNumber"] == "1-F1"
    assert flow["totalScore"] == 50
    assert redis.hashes["interview:follow_up_questions:session:session-1"] == {
        "1-F1": "How would you handle retries?"
    }
    assert len(follow_up_agent.calls) == 1


@pytest.mark.anyio
async def test_follow_up_answer_advances_main_question_without_adding_score() -> None:
    database = Database()
    redis = RedisStub()
    redis.hashes["interview:follow_up_questions:session:session-1"] = {
        "1-F1": "How would you handle retries?"
    }
    redis.values["interview:flow:session:session-1"] = json.dumps(
        {
            "status": "FOLLOW_UP",
            "currentIndex": 0,
            "currentQuestionNumber": "1-F1",
            "totalQuestions": 2,
            "followUpCount": 1,
            "maxFollowUp": 2,
            "version": 3,
            "totalScore": 50,
            "finished": False,
        }
    )
    service = InterviewAnswerService(
        database,  # type: ignore[arg-type]
        redis,  # type: ignore[arg-type]
        StrongFollowUpScorer(),
        follow_up_agent=UnexpectedFollowUpAgent(),  # type: ignore[arg-type]
    )

    response = await service.submit(
        "session-1", 42, "1-F1", "Use exponential backoff", "request-clarify"
    )

    flow = json.loads(redis.values["interview:flow:session:session-1"])
    turn = database.collections["interview_turn"].inserted[0]
    assert response["questionNumber"] == "1-F1"
    assert response["score"] == 90
    assert response["totalScore"] == 50
    assert response["nextQuestionNumber"] == "2"
    assert response["isFollowUp"] is False
    assert flow["status"] == "ASKING"
    assert flow["currentQuestionNumber"] == "2"
    assert flow["followUpCount"] == 0
    assert flow["totalScore"] == 50
    assert turn["followUpNeeded"] is False
    assert turn["isFollowUp"] is True
    assert turn["followUpCount"] == 1
    assert turn["finished"] is False


@pytest.mark.anyio
async def test_completed_legacy_flow_rejects_answer_as_business_conflict() -> None:
    database = Database()
    redis = RedisStub()
    redis.values["interview:flow:session:session-1"] = json.dumps(
        {
            "status": "COMPLETED",
            "currentQuestionNumber": "2",
            "totalQuestions": 2,
            "totalScore": 120,
            "finished": True,
        }
    )
    service = InterviewAnswerService(
        database,  # type: ignore[arg-type]
        redis,  # type: ignore[arg-type]
        SuccessfulScorer(),
    )

    with pytest.raises(BusinessError) as error:
        await service.submit("session-1", 42, "2", "Again", "completed-request")

    assert error.value.code == "A000409"
    assert error.value.message == "面试流程已经完成"


@pytest.mark.anyio
async def test_answer_repairs_redis_replay_from_durable_turn_archive() -> None:
    database = Database()
    archived_response = {
        "questionNumber": "1",
        "questionContent": "First question",
        "isSuccess": True,
        "finished": False,
        "isFollowUp": False,
        "followUpCount": 0,
        "score": 80,
        "totalScore": 80,
        "feedback": "Good",
        "missingPoints": [],
        "followUpNeeded": False,
        "followUpQuestion": None,
        "nextQuestionNumber": "2",
        "nextQuestion": "Second question",
    }
    database.collections["interview_turn"].document = {
        "sessionId": "session-1",
        "userId": 42,
        "requestId": "request-archived",
        "response": archived_response,
    }
    redis = RedisStub()
    service = InterviewAnswerService(database, redis, UnexpectedScorer())  # type: ignore[arg-type]

    response = await service.submit(
        "session-1", 42, "1", "My answer", "request-archived"
    )

    assert response == archived_response
    assert json.loads(
        redis.values[
            "interview:answer:replay:session-1:request-archived"
        ]
    ) == archived_response
    assert database.collections["interview_turn"].inserted == []
