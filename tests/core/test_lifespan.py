import asyncio
from dataclasses import dataclass

import pytest
from fastapi import FastAPI

from app.core import lifespan as lifespan_module
from app.core.lifespan import AppResources, lifespan
from app.core.settings import Settings


@dataclass
class FakeEngine:
    disposed: int = 0

    async def dispose(self) -> None:
        self.disposed += 1


@dataclass
class FakeMongo:
    closed: int = 0

    async def close(self) -> None:
        self.closed += 1


class FakePubSub:
    def __init__(self) -> None:
        self.channels: list[str] = []
        self.closed = 0
        self._released = asyncio.Event()

    async def subscribe(self, *channels: str) -> None:
        self.channels.extend(channels)

    async def listen(self):
        await self._released.wait()
        if False:
            yield None

    async def unsubscribe(self, *channels: str) -> None:
        del channels
        self._released.set()

    async def aclose(self) -> None:
        self.closed += 1
        self._released.set()


@dataclass
class FakeRedis:
    closed: int = 0

    def __post_init__(self) -> None:
        self.pubsubs: list[FakePubSub] = []

    def pubsub(self) -> FakePubSub:
        pubsub = FakePubSub()
        self.pubsubs.append(pubsub)
        return pubsub

    async def aclose(self) -> None:
        self.closed += 1


@dataclass
class FakeHttp:
    closed: int = 0

    async def aclose(self) -> None:
        self.closed += 1


@pytest.mark.anyio
async def test_lifespan_creates_and_closes_shared_resources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = FakeEngine()
    mongo = FakeMongo()
    redis = FakeRedis()
    http = FakeHttp()
    resources = AppResources(
        engine=engine,
        session_factory=object(),
        mongo_client=mongo,
        mongo_database=object(),
        redis=redis,
        http=http,
    )

    def fake_build_resources(_: Settings) -> AppResources:
        return resources

    schema_calls = 0

    async def fake_ensure_mysql_schema(candidate: object) -> None:
        nonlocal schema_calls
        assert candidate is engine
        schema_calls += 1

    monkeypatch.setattr(lifespan_module, "build_resources", fake_build_resources)
    monkeypatch.setattr(
        lifespan_module, "ensure_mysql_schema", fake_ensure_mysql_schema
    )
    app = FastAPI()

    async with lifespan(app):
        assert app.state.resources is resources
        assert [pubsub.channels for pubsub in redis.pubsubs] == [
            ["configuration:invalidation"],
            [app.state.websocket_push_service.routing.node_channel],
        ]
        task_names = {task.get_name() for task in asyncio.all_tasks()}
        assert "interview-turn-repair" in task_names
        assert "agent-file-repair" in task_names

    assert engine.disposed == 1
    assert schema_calls == 1
    assert mongo.closed == 1
    assert redis.closed == 1
    assert http.closed == 1
    assert all(pubsub.closed == 1 for pubsub in redis.pubsubs)
