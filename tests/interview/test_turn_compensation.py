import json

import pytest

from app.interview.application.turn_compensation import (
    TURN_COMPENSATION_FAILED_KEY,
    TURN_COMPENSATION_KEY,
    TurnCompensationQueue,
)
from app.workers.repair_interview_turn import repair_turn_once


class Redis:
    def __init__(self) -> None:
        self.values: dict[str, list[str]] = {}

    async def lpush(self, key: str, value: str) -> None:
        self.values.setdefault(key, []).insert(0, value)

    async def rpop(self, key: str):
        values = self.values.get(key, [])
        return values.pop() if values else None


@pytest.mark.anyio
async def test_turn_compensation_retries_at_most_three_times() -> None:
    redis = Redis()
    queue = TurnCompensationQueue(redis)
    await queue.enqueue({"requestId": "r1"})

    attempts = 0

    async def failing(turn):
        nonlocal attempts
        attempts += 1
        raise RuntimeError("mongo down")

    assert await queue.process_one(failing) is False
    assert await queue.process_one(failing) is False
    assert await queue.process_one(failing) is False
    assert attempts == 3
    assert not redis.values.get(TURN_COMPENSATION_KEY)
    failed = json.loads(redis.values[TURN_COMPENSATION_FAILED_KEY][0])
    assert failed["requestId"] == "r1"
    assert failed["retryCount"] == 3


@pytest.mark.anyio
async def test_turn_compensation_requeues_retryable_failure() -> None:
    redis = Redis()
    queue = TurnCompensationQueue(redis)
    await queue.enqueue({"requestId": "r2"})
    calls = 0

    async def succeeds(turn):
        nonlocal calls
        calls += 1

    assert await queue.process_one(succeeds) is True
    assert calls == 1


@pytest.mark.anyio
async def test_turn_compensation_payload_has_stable_repair_identity() -> None:
    redis = Redis()
    queue = TurnCompensationQueue(redis)

    await queue.enqueue(
        {"sessionId": "s1", "requestId": "r1", "seq": 7}
    )

    payload = json.loads(redis.values[TURN_COMPENSATION_KEY][0])
    assert payload["messageId"]
    assert payload["mutationId"] == "r1"
    assert payload["sessionId"] == "s1"
    assert payload["requestId"] == "r1"
    assert payload["seq"] == 7
    assert payload["retryCount"] == 0


class TurnCollection:
    def __init__(self) -> None:
        self.documents: list[dict[str, object]] = []

    async def find_one(self, query):
        return next(
            (
                item
                for item in self.documents
                if all(item.get(key) == value for key, value in query.items())
            ),
            None,
        )

    async def insert_one(self, document):
        self.documents.append(document)


class Database:
    def __init__(self) -> None:
        self.turns = TurnCollection()

    def __getitem__(self, name):
        assert name == "interview_turn"
        return self.turns


@pytest.mark.anyio
async def test_turn_repair_worker_is_idempotent_by_request_id() -> None:
    redis = Redis()
    database = Database()
    queue = TurnCompensationQueue(redis)
    turn = {"sessionId": "s1", "requestId": "r1", "score": 80}
    await queue.enqueue(turn)
    await queue.enqueue(turn)

    assert await repair_turn_once(redis, database) is True
    assert await repair_turn_once(redis, database) is True
    assert database.turns.documents == [turn]
