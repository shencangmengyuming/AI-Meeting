import json

import pytest


class RedisRuntimeStub:
    def __init__(self, value: dict[str, object] | None = None) -> None:
        self.value = value

    async def get(self, key: str):
        return json.dumps(self.value) if self.value is not None else None

    async def set(self, key: str, value: str, *, ex: int | None = None):
        self.value = json.loads(value)
        return True


class MongoCollectionStub:
    def __init__(self, document: dict[str, object] | None = None) -> None:
        self.document = document
        self.writes: list[dict[str, object]] = []

    async def find_one(self, query: dict[str, object]):
        return self.document

    async def replace_one(
        self,
        query: dict[str, object],
        document: dict[str, object],
        *,
        upsert: bool,
    ):
        self.document = document
        self.writes.append(document)
        return type("Result", (), {"matched_count": 1})()


class TurnCollectionStub:
    def __init__(self, documents: list[dict[str, object]]) -> None:
        self.documents = documents

    def find(self, query: dict[str, object]):
        documents = [
            item
            for item in self.documents
            if all(item.get(key) == value for key, value in query.items())
        ]

        class Cursor:
            async def to_list(self, length=None):
                del length
                return documents

        return Cursor()


@pytest.mark.anyio
async def test_runtime_prefers_ready_redis_state() -> None:
    from app.interview.application.runtime_rehydrate import RuntimeRehydrator

    redis = RedisRuntimeStub({"sessionId": "s1", "status": "ASKING", "version": 3})
    mongo = MongoCollectionStub({"sessionId": "s1", "status": "COLD"})

    view = await RuntimeRehydrator(redis, mongo).ensure_runtime("s1")

    assert view.source == "REDIS"
    assert view.state["status"] == "ASKING"
    assert mongo.writes == []


@pytest.mark.anyio
async def test_runtime_restores_snapshot_when_redis_is_empty() -> None:
    from app.interview.application.runtime_rehydrate import RuntimeRehydrator

    redis = RedisRuntimeStub()
    mongo = MongoCollectionStub(
        {"sessionId": "s1", "status": "ASKING", "version": 4}
    )

    view = await RuntimeRehydrator(redis, mongo).ensure_runtime("s1")

    assert view.source == "MONGO_SNAPSHOT"
    assert view.state["version"] == 4
    assert redis.value == view.state


@pytest.mark.anyio
async def test_runtime_rebuilds_from_latest_turn_when_snapshot_is_missing() -> None:
    from app.interview.application.runtime_rehydrate import RuntimeRehydrator

    redis = RedisRuntimeStub()
    snapshot = MongoCollectionStub()
    turns = TurnCollectionStub(
        [
            {
                "sessionId": "s1",
                "requestId": "r1",
                "totalScore": 80,
                "nextQuestionNumber": "2",
                "finished": False,
                "followUpCount": 0,
                "createTime": "2026-01-01T00:00:00Z",
            },
            {
                "sessionId": "s1",
                "requestId": "r2",
                "totalScore": 150,
                "nextQuestionNumber": "2-F1",
                "finished": False,
                "followUpCount": 1,
                "createTime": "2026-01-01T00:00:01Z",
            },
        ]
    )

    view = await RuntimeRehydrator(redis, snapshot, turns).ensure_runtime("s1")

    assert view.source == "TURN_ARCHIVE"
    assert view.confidence == "MEDIUM"
    assert view.state == {
        "sessionId": "s1",
        "status": "FOLLOW_UP",
        "currentQuestionNumber": "2-F1",
        "followUpCount": 1,
        "totalScore": 150,
        "finished": False,
        "version": 2,
        "lastRequestId": "r2",
    }
    assert redis.value == view.state


@pytest.mark.anyio
async def test_runtime_snapshot_uses_version_and_mutation_id_for_idempotency() -> None:
    from app.interview.application.runtime_rehydrate import RuntimeRehydrator

    redis = RedisRuntimeStub()
    mongo = MongoCollectionStub(
        {"sessionId": "s1", "status": "ASKING", "version": 2, "mutationId": "m1"}
    )
    runtime = RuntimeRehydrator(redis, mongo)

    first = await runtime.refresh_snapshot(
        "s1", {"status": "EVALUATING"}, mutation_id="m2", expected_version=2
    )
    second = await runtime.refresh_snapshot(
        "s1", {"status": "EVALUATING"}, mutation_id="m2", expected_version=2
    )

    assert first.version == 3
    assert second.version == 3
    assert len(mongo.writes) == 1


@pytest.mark.anyio
async def test_snapshot_rejects_cas_miss_before_refreshing_redis() -> None:
    from app.interview.application.runtime_rehydrate import RuntimeRehydrator

    class MissCollection(MongoCollectionStub):
        async def replace_one(self, query, document, *, upsert):
            return type(
                "Result", (), {"matched_count": 0, "upserted_id": None}
            )()

    redis = RedisRuntimeStub()
    mongo = MissCollection({"sessionId": "s1", "version": 1})

    with pytest.raises(RuntimeError, match="version conflict"):
        await RuntimeRehydrator(redis, mongo).refresh_snapshot(
            "s1",
            {"status": "ASKING"},
            mutation_id="m2",
            expected_version=1,
        )

    assert redis.value is None


@pytest.mark.anyio
async def test_existing_snapshot_uses_non_upsert_cas_update() -> None:
    from app.interview.application.runtime_rehydrate import RuntimeRehydrator

    class ExistingSnapshotCollection(MongoCollectionStub):
        def __init__(self) -> None:
            super().__init__({"sessionId": "s1", "version": 2})
            self.upsert_values: list[bool] = []

        async def replace_one(self, query, document, *, upsert):
            self.upsert_values.append(upsert)
            return type("Result", (), {"matched_count": 1, "upserted_id": None})()

    mongo = ExistingSnapshotCollection()
    redis = RedisRuntimeStub()

    await RuntimeRehydrator(redis, mongo).refresh_snapshot(
        "s1", {"status": "ASKING"}, mutation_id="m2", expected_version=2
    )

    assert mongo.upsert_values == [False]


@pytest.mark.anyio
async def test_missing_snapshot_allows_only_initial_version_upsert() -> None:
    from app.interview.application.runtime_rehydrate import RuntimeRehydrator

    class InitialSnapshotCollection(MongoCollectionStub):
        def __init__(self) -> None:
            super().__init__()
            self.upsert_values: list[bool] = []

        async def replace_one(self, query, document, *, upsert):
            self.upsert_values.append(upsert)
            self.document = document
            return type("Result", (), {"matched_count": 0, "upserted_id": "new"})()

    mongo = InitialSnapshotCollection()
    redis = RedisRuntimeStub()

    await RuntimeRehydrator(redis, mongo).refresh_snapshot(
        "s1", {"status": "INIT"}, mutation_id="m1", expected_version=0
    )

    assert mongo.upsert_values == [True]
