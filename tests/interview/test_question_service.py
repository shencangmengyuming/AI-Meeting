import json
from typing import Any

import pytest

from app.interview.application.questions import InterviewQuestionService


class Collection:
    async def find_one(self, *args: object, **kwargs: object):
        return {"_id": "session"}


class Database:
    def __getitem__(self, name: str) -> Collection:
        return Collection()


class RecoveryTurnCollection(Collection):
    def __init__(self) -> None:
        self.turns = [
            {
                "sessionId": "session-1",
                "nextQuestionNumber": "2",
                "nextQuestion": "Second",
                "finished": False,
                "followUpCount": 0,
                "totalScore": 80,
                "createTime": 2,
            }
        ]

    def find(self, query):
        return self.turns


class RecoveryDatabase(Database):
    def __getitem__(self, name: str):
        if name == "interview_turn":
            return RecoveryTurnCollection()
        return super().__getitem__(name)


class RedisStub:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.hashes: dict[str, dict[Any, Any]] = {}

    async def get(self, key: str):
        return self.values.get(key)

    async def set(self, key: str, value: str, ex: int):
        self.values[key] = value

    async def hgetall(self, key: str):
        return self.hashes.get(key, {})

    async def hset(self, key: str, mapping: dict[str, str]):
        self.hashes[key] = mapping


@pytest.mark.anyio
async def test_question_read_initializes_and_reuses_flow_cursor() -> None:
    redis = RedisStub()
    redis.hashes["interview:questions:session:session-1"] = {
        "1": "First",
        "2": "Second",
    }
    service = InterviewQuestionService(Database(), redis)  # type: ignore[arg-type]

    first = await service.get_first_question("session-1", 42)
    flow = json.loads(redis.values["interview:flow:session:session-1"])
    second = await service.get_first_question("session-1", 42)

    assert first["questionNumber"] == "1"
    assert second["questionContent"] == "First"
    assert flow == {
        "status": "ASKING",
        "currentQuestionNumber": "1",
        "totalQuestions": 2,
        "finished": False,
    }


@pytest.mark.anyio
async def test_question_cache_decodes_real_redis_byte_values() -> None:
    redis = RedisStub()
    redis.hashes["interview:questions:session:session-1"] = {
        b"1": b"First",
        b"2": b"Second",
    }
    redis.hashes["interview:follow_up_questions:session:session-1"] = {
        b"1-F1": b"Explain retries",
    }
    service = InterviewQuestionService(Database(), redis)  # type: ignore[arg-type]

    questions = await service.get_questions("session-1", 42)
    follow_up = await service.get_follow_up_question("session-1", "1-F1")

    assert questions == {"1": "First", "2": "Second"}
    assert follow_up == "Explain retries"


@pytest.mark.anyio
async def test_current_question_reads_active_follow_up_from_follow_up_cache() -> None:
    redis = RedisStub()
    redis.hashes["interview:questions:session:session-1"] = {"1": "First"}
    redis.hashes["interview:follow_up_questions:session:session-1"] = {
        "1-F1": "Explain retries"
    }
    redis.values["interview:flow:session:session-1"] = json.dumps(
        {
            "status": "FOLLOW_UP",
            "currentQuestionNumber": "1-F1",
            "totalQuestions": 1,
            "finished": False,
        }
    )
    service = InterviewQuestionService(Database(), redis)  # type: ignore[arg-type]

    current = await service.get_first_question("session-1", 42)

    assert current["questionNumber"] == "1-F1"
    assert current["questionContent"] == "Explain retries"


@pytest.mark.anyio
async def test_current_question_returns_terminal_snapshot_when_flow_finished() -> None:
    redis = RedisStub()
    redis.hashes["interview:questions:session:session-1"] = {"1": "First"}
    redis.values["interview:flow:session:session-1"] = json.dumps(
        {
            "status": "COMPLETED",
            "currentQuestionNumber": None,
            "totalQuestions": 1,
            "finished": True,
        }
    )
    service = InterviewQuestionService(Database(), redis)  # type: ignore[arg-type]

    current = await service.get_first_question("session-1", 42)

    assert current == {
        "questionNumber": None,
        "questionContent": None,
        "isSuccess": True,
        "finished": True,
    }


@pytest.mark.anyio
async def test_current_question_recovers_archived_flow() -> None:
    redis = RedisStub()
    redis.hashes["interview:questions:session:session-1"] = {
        "1": "First",
        "2": "Second",
    }
    service = InterviewQuestionService(RecoveryDatabase(), redis)  # type: ignore[arg-type]

    current = await service.get_first_question("session-1", 42)

    assert current["questionNumber"] == "2"
    assert current["questionContent"] == "Second"
