import asyncio
import itertools
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from typing import cast

import pytest
from redis.asyncio import Redis
from redis.exceptions import ConnectionError
from testcontainers.core.container import DockerContainer

from app.auth_user.domain.session import AuthIdentity, AuthPrincipal
from app.auth_user.infrastructure.redis_session import RedisSessionAdapter
from app.infrastructure.redis import create_redis_resource

USERNAME = "fixture-user"
TOKEN_TIMEOUT_SECONDS = 2_592_000


class InMemoryIdentityLookup:
    def __init__(self, identities: dict[str, AuthIdentity]) -> None:
        self._identities = identities

    async def find_by_username(self, username: str) -> AuthIdentity | None:
        return self._identities.get(username)


@pytest.fixture(scope="module")
def redis_url() -> Iterator[str]:
    with DockerContainer("redis:7").with_exposed_ports(6379) as container:
        yield f"redis://{container.get_container_host_ip()}:{container.get_exposed_port(6379)}/0"


@pytest.fixture
async def redis_client(redis_url: str) -> AsyncIterator[Redis]:
    redis = create_redis_resource(redis_url)
    for _ in range(30):
        try:
            await cast(Awaitable[bool], redis.ping())
            break
        except ConnectionError:
            await asyncio.sleep(0.2)
    else:
        pytest.fail("Redis container did not become ready")
    await redis.flushdb()
    try:
        yield redis
    finally:
        await redis.aclose()


def _adapter(
    redis: Redis,
    token_factory: Callable[[], str] = lambda: "candidate-token",
) -> RedisSessionAdapter:
    lookup = InMemoryIdentityLookup(
        {
            USERNAME: AuthIdentity(
                user_id=42,
                username=USERNAME,
                roles=frozenset({"user"}),
            )
        }
    )
    return RedisSessionAdapter(
        redis,
        lookup,
        token_factory=token_factory,
        clock_ms=lambda: 1_795_030_004_920,
    )


@pytest.mark.integration
@pytest.mark.anyio
async def test_login_and_resolve(redis_client: Redis) -> None:
    adapter = _adapter(redis_client)
    token = await adapter.login(USERNAME)

    assert await adapter.resolve(token.value) == AuthPrincipal(
        user_id=42,
        username=USERNAME,
        token=token.value,
        roles=frozenset({"user"}),
    )
    assert await redis_client.get(adapter.keys.token(token.value)) == USERNAME.encode()


@pytest.mark.integration
@pytest.mark.anyio
async def test_login_reuses_active_session(redis_client: Redis) -> None:
    candidates = iter(("first-token", "second-token"))
    adapter = _adapter(redis_client, lambda: next(candidates))

    first = await adapter.login(USERNAME)
    second = await adapter.login(USERNAME)

    assert first.value == second.value == "first-token"
    assert await redis_client.ttl(adapter.keys.token(first.value)) > 2_591_990


@pytest.mark.integration
@pytest.mark.anyio
async def test_concurrent_login_calls_share_one_token(redis_client: Redis) -> None:
    counter = itertools.count(1)
    adapter = _adapter(redis_client, lambda: f"candidate-{next(counter)}")

    tokens = await asyncio.gather(*(adapter.login(USERNAME) for _ in range(8)))

    assert {token.value for token in tokens} == {"candidate-1"}


@pytest.mark.integration
@pytest.mark.anyio
async def test_expired_or_unknown_token_is_rejected(redis_client: Redis) -> None:
    adapter = _adapter(redis_client)
    await redis_client.set(adapter.keys.token("expired"), USERNAME, px=1)
    await asyncio.sleep(0.02)

    assert await adapter.resolve("expired") is None
    assert await adapter.resolve("unknown") is None


@pytest.mark.integration
@pytest.mark.anyio
async def test_logout_removes_session_and_token(redis_client: Redis) -> None:
    adapter = _adapter(redis_client)
    token = await adapter.login(USERNAME)

    await adapter.logout(token.value)

    assert await redis_client.exists(adapter.keys.token(token.value)) == 0
    assert await redis_client.exists(adapter.keys.session(USERNAME)) == 0
