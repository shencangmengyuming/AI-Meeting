import asyncio
from collections.abc import Awaitable
from typing import cast

import pytest
from redis.exceptions import ConnectionError
from testcontainers.core.container import DockerContainer

from app.infrastructure.redis import create_redis_resource


@pytest.mark.integration
@pytest.mark.anyio
async def test_redis_resource_supports_ttl_and_lua_cas() -> None:
    with DockerContainer("redis:7").with_exposed_ports(6379) as container:
        host = container.get_container_host_ip()
        port = container.get_exposed_port(6379)
        redis = create_redis_resource(f"redis://{host}:{port}/0")
        try:
            for _ in range(30):
                try:
                    await cast(Awaitable[bool], redis.ping())
                    break
                except ConnectionError:
                    await asyncio.sleep(0.2)
            else:
                pytest.fail("Redis container did not become ready")
            await redis.set("probe", "one", ex=30)
            assert await redis.get("probe") == b"one"
            assert await redis.ttl("probe") > 0
            script = redis.register_script(
                """
                if redis.call('GET', KEYS[1]) == ARGV[1] then
                    redis.call('SET', KEYS[1], ARGV[2])
                    return 1
                end
                return 0
                """
            )
            assert await script(keys=["probe"], args=["one", "two"]) == 1
            assert await redis.get("probe") == b"two"
            assert await script(keys=["probe"], args=["one", "three"]) == 0
        finally:
            await redis.aclose()
