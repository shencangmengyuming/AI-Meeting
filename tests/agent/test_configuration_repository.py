from contextlib import asynccontextmanager
from typing import Any

import pytest

from app.agent.infrastructure.configuration import (
    CachedAgentConfigurationRepository,
    MySqlAgentConfigurationRepository,
)


class MappingResult:
    def __init__(self, row: dict[str, object] | None) -> None:
        self.row = row

    def mappings(self) -> "MappingResult":
        return self

    def first(self) -> dict[str, object] | None:
        return self.row


class Session:
    def __init__(self, row: dict[str, object] | None) -> None:
        self.row = row
        self.params: dict[str, Any] | None = None

    async def execute(self, statement: object, params: dict[str, Any]) -> MappingResult:
        self.params = params
        return MappingResult(self.row)


class SessionFactory:
    def __init__(self, row: dict[str, object] | None) -> None:
        self.session = Session(row)

    @asynccontextmanager
    async def __call__(self):
        yield self.session


@pytest.mark.anyio
async def test_repository_resolves_scene_with_alias_and_masks_secret() -> None:
    factory = SessionFactory(
        {
            "id": 9,
            "agent_name": "面试提问官",
            "api_key": "abcd1234",
            "api_secret": "secret",
            "api_flow_id": "flow-1",
        }
    )
    repository = MySqlAgentConfigurationRepository(factory)  # type: ignore[arg-type]

    configuration = await repository.resolve("follow_up", aliases=("面试提问官",))

    assert configuration.agent_id == 9
    assert configuration.to_public_dict()["apiKey"] == "abcd****234"
    assert configuration.to_public_dict()["apiSecret"] is None
    assert factory.session.params == {
        "scene_name": "follow_up",
        "alias_name": "面试提问官",
    }


@pytest.mark.anyio
async def test_repository_rejects_missing_configuration() -> None:
    repository = MySqlAgentConfigurationRepository(SessionFactory(None))  # type: ignore[arg-type]

    with pytest.raises(LookupError, match="agent configuration not found"):
        await repository.resolve("general")


@pytest.mark.anyio
async def test_repository_resolves_configuration_by_bound_agent_id() -> None:
    factory = SessionFactory(
        {
            "id": 42,
            "agent_name": "general",
            "api_key": "key",
            "api_secret": "secret",
            "api_flow_id": "flow",
        }
    )
    repository = MySqlAgentConfigurationRepository(factory)  # type: ignore[arg-type]

    configuration = await repository.resolve_by_id(42)

    assert configuration.agent_id == 42
    assert factory.session.params == {"agent_id": 42}


class MutableRepository:
    def __init__(self) -> None:
        self.calls = 0

    async def resolve(self, scene: str, aliases=()):
        from app.agent.domain.configuration import AgentConfiguration

        self.calls += 1
        return AgentConfiguration(
            agent_id=self.calls,
            name=scene,
            api_key=f"key-{self.calls}",
            api_secret=f"secret-{self.calls}",
            flow_id=f"flow-{self.calls}",
        )

    async def resolve_by_id(self, agent_id: int):
        return await self.resolve(str(agent_id))


class PubSub:
    async def listen(self):
        yield {"type": "subscribe", "data": 1}
        yield {"type": "message", "data": b"agent"}


@pytest.mark.anyio
async def test_cached_repository_reloads_after_invalidation_event() -> None:
    delegate = MutableRepository()
    repository = CachedAgentConfigurationRepository(delegate)

    first = await repository.resolve("general")
    cached = await repository.resolve("general")
    await repository.consume_invalidations(PubSub(), __import__("asyncio").Event())
    refreshed = await repository.resolve("general")

    assert first.agent_id == cached.agent_id == 1
    assert refreshed.agent_id == 2
    assert delegate.calls == 2
