import asyncio
from collections.abc import Mapping, Sequence
from typing import Any, Protocol

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agent.domain.configuration import AgentConfiguration


class AgentConfigurationRepository(Protocol):
    async def resolve(
        self, scene: str, aliases: Sequence[str] = ()
    ) -> AgentConfiguration: ...

    async def resolve_by_id(self, agent_id: int) -> AgentConfiguration: ...


class MySqlAgentConfigurationRepository:
    """Resolve active Agent credentials from the Python-owned database."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.session_factory = session_factory

    async def resolve(
        self, scene: str, aliases: Sequence[str] = ()
    ) -> AgentConfiguration:
        alias_name = aliases[0] if aliases else scene
        async with self.session_factory() as session:
            result = await session.execute(
                text(
                    "SELECT id, agent_name, api_secret, api_key, api_flow_id "
                    "FROM agent_properties "
                    "WHERE del_flag = 0 AND agent_name IN (:scene_name, :alias_name) "
                    "ORDER BY CASE agent_name WHEN :scene_name THEN 0 "
                    "WHEN :alias_name THEN 1 ELSE 2 END LIMIT 1"
                ),
                {"scene_name": scene, "alias_name": alias_name},
            )
            row = result.mappings().first()

        if row is None:
            raise LookupError(f"agent configuration not found for scene: {scene}")
        return _configuration(row, f"scene: {scene}")

    async def resolve_by_id(self, agent_id: int) -> AgentConfiguration:
        async with self.session_factory() as session:
            result = await session.execute(
                text(
                    "SELECT id, agent_name, api_secret, api_key, api_flow_id "
                    "FROM agent_properties WHERE del_flag = 0 AND id = :agent_id "
                    "LIMIT 1"
                ),
                {"agent_id": agent_id},
            )
            row = result.mappings().first()
        if row is None:
            raise LookupError(f"agent configuration not found for id: {agent_id}")
        return _configuration(row, f"id: {agent_id}")


def _configuration(row: Mapping[Any, Any], subject: str) -> AgentConfiguration:
    required = ("id", "agent_name", "api_key", "api_secret", "api_flow_id")
    if any(row.get(key) is None or not str(row[key]).strip() for key in required):
        raise ValueError(f"agent configuration incomplete for {subject}")
    return AgentConfiguration(
        agent_id=int(str(row["id"])),
        name=str(row["agent_name"]).strip(),
        api_key=str(row["api_key"]).strip(),
        api_secret=str(row["api_secret"]).strip(),
        flow_id=str(row["api_flow_id"]).strip(),
    )


class StaticAgentConfigurationRepository:
    """Small in-memory repository useful for local wiring and tests."""

    def __init__(self, configurations: Mapping[str, AgentConfiguration]) -> None:
        self.configurations = dict(configurations)

    async def resolve(
        self, scene: str, aliases: Sequence[str] = ()
    ) -> AgentConfiguration:
        for name in (scene, *aliases):
            if name in self.configurations:
                return self.configurations[name]
        raise LookupError(f"agent configuration not found for scene: {scene}")

    async def resolve_by_id(self, agent_id: int) -> AgentConfiguration:
        for configuration in self.configurations.values():
            if configuration.agent_id == agent_id:
                return configuration
        raise LookupError(f"agent configuration not found for id: {agent_id}")


class CachedAgentConfigurationRepository:
    def __init__(self, delegate: AgentConfigurationRepository) -> None:
        self.delegate = delegate
        self._cache: dict[tuple[str, tuple[str, ...]], AgentConfiguration] = {}
        self._lock = asyncio.Lock()

    async def resolve(
        self, scene: str, aliases: Sequence[str] = ()
    ) -> AgentConfiguration:
        key = (scene, tuple(aliases))
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        configuration = await self.delegate.resolve(scene, aliases)
        async with self._lock:
            self._cache[key] = configuration
        return configuration

    async def invalidate(self) -> None:
        async with self._lock:
            self._cache.clear()

    async def resolve_by_id(self, agent_id: int) -> AgentConfiguration:
        key = (f"id:{agent_id}", ())
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        configuration = await self.delegate.resolve_by_id(agent_id)
        async with self._lock:
            self._cache[key] = configuration
        return configuration

    async def consume_invalidations(self, pubsub, stop_event: asyncio.Event) -> None:
        async for message in pubsub.listen():
            if stop_event.is_set():
                return
            if message.get("type") == "message":
                await self.invalidate()
