import asyncio
import json
from collections.abc import Awaitable
from typing import cast

import pytest
from redis.exceptions import ConnectionError
from testcontainers.core.container import DockerContainer

from app.ai_runtime.application.singleflight import DistributedSingleFlight
from app.infrastructure.redis import create_redis_resource


async def _ready(redis) -> None:
    for _ in range(30):
        try:
            await cast(Awaitable[bool], redis.ping())
            return
        except ConnectionError:
            await asyncio.sleep(0.2)
    pytest.fail("Redis container did not become ready")


@pytest.mark.integration
@pytest.mark.anyio
async def test_atomic_singleflight_has_one_owner_and_distributed_follower() -> None:
    with DockerContainer("redis:7").with_exposed_ports(6379) as container:
        redis = create_redis_resource(
            f"redis://{container.get_container_host_ip()}:"
            f"{container.get_exposed_port(6379)}/0"
        )
        await _ready(redis)
        first = DistributedSingleFlight(redis, ttl_seconds=5)
        second = DistributedSingleFlight(redis, ttl_seconds=5)
        calls = 0

        async def supplier() -> str:
            nonlocal calls
            calls += 1
            await asyncio.sleep(0.05)
            return "ok"

        try:
            results = await asyncio.gather(
                first.execute("score", "same", supplier),
                second.execute("score", "same", supplier),
            )
            assert calls == 1
            assert [result.result for result in results] == ["ok", "ok"]
            assert {result.action for result in results} == {
                "OWNER_NEW",
                "REPLAY_SUCCESS",
            }
        finally:
            await redis.aclose()


@pytest.mark.integration
@pytest.mark.anyio
async def test_fenced_owner_cannot_publish_after_ownership_changes() -> None:
    with DockerContainer("redis:7").with_exposed_ports(6379) as container:
        redis = create_redis_resource(
            f"redis://{container.get_container_host_ip()}:"
            f"{container.get_exposed_port(6379)}/0"
        )
        await _ready(redis)
        service = DistributedSingleFlight(redis, ttl_seconds=5)

        async def supplier() -> str:
            key = "ai:flight:score:fenced"
            await redis.set(
                key,
                json.dumps(
                    {
                        "status": "RUNNING",
                        "owner": "new-owner",
                        "fencing": 99,
                        "heartbeat": 1,
                    }
                ),
                ex=5,
            )
            return "stale"

        try:
            result = await service.execute("score", "fenced", supplier)
            assert result.result is None
            assert result.error == "single-flight owner lost fencing token"
        finally:
            await redis.aclose()
