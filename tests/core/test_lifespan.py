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

    def close(self) -> None:
        self.closed += 1


@dataclass
class FakeRedis:
    closed: int = 0

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

    monkeypatch.setattr(lifespan_module, "build_resources", fake_build_resources)
    app = FastAPI()

    async with lifespan(app):
        assert app.state.resources is resources

    assert engine.disposed == 1
    assert mongo.closed == 1
    assert redis.closed == 1
    assert http.closed == 1
