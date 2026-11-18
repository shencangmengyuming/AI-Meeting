import asyncio
import itertools
import json
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from typing import cast

import pytest
from redis.asyncio import Redis
from redis.exceptions import ConnectionError
from testcontainers.core.container import DockerContainer

from app.auth_user.domain.session import AuthIdentity, AuthPrincipal
from app.auth_user.infrastructure.java_satoken import JavaSaTokenAdapter
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
        host = container.get_container_host_ip()
        port = container.get_exposed_port(6379)
        yield f"redis://{host}:{port}/0"


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
) -> JavaSaTokenAdapter:
    lookup = InMemoryIdentityLookup(
        {
            USERNAME: AuthIdentity(
                user_id=42,
                username=USERNAME,
                roles=frozenset({"user"}),
            )
        }
    )
    return JavaSaTokenAdapter(
        redis,
        lookup,
        token_factory=token_factory,
        clock_ms=lambda: 1_795_030_004_920,
    )


@pytest.mark.integration
@pytest.mark.anyio
async def test_resolve_returns_principal_for_java_token(
    redis_client: Redis,
) -> None:
    adapter = _adapter(redis_client)
    await redis_client.set(
        "Authorization:login:token:java-token",
        USERNAME,
        ex=TOKEN_TIMEOUT_SECONDS,
    )

    principal = await adapter.resolve("java-token")

    assert principal == AuthPrincipal(
        user_id=42,
        username=USERNAME,
        token="java-token",
        roles=frozenset({"user"}),
    )


@pytest.mark.integration
@pytest.mark.anyio
async def test_resolve_returns_none_for_expired_token(redis_client: Redis) -> None:
    adapter = _adapter(redis_client)
    await redis_client.set(
        "Authorization:login:token:expired-token", USERNAME, px=1
    )
    await asyncio.sleep(0.02)

    assert await adapter.resolve("expired-token") is None


@pytest.mark.integration
@pytest.mark.anyio
async def test_resolve_returns_none_when_identity_is_missing(
    redis_client: Redis,
) -> None:
    adapter = JavaSaTokenAdapter(
        redis_client,
        InMemoryIdentityLookup({}),
        token_factory=lambda: "candidate-token",
    )
    await redis_client.set(
        "Authorization:login:token:orphan-token",
        "missing-user",
        ex=TOKEN_TIMEOUT_SECONDS,
    )

    assert await adapter.resolve("orphan-token") is None


@pytest.mark.integration
@pytest.mark.anyio
async def test_login_writes_java_readable_session_and_reuses_token(
    redis_client: Redis,
) -> None:
    candidates = iter(("first-token", "second-token"))
    adapter = _adapter(redis_client, lambda: next(candidates))

    first = await adapter.login(USERNAME)
    await redis_client.expire(adapter.keys.token(first.value), 30)
    await redis_client.expire(adapter.keys.session(USERNAME), 30)
    second = await adapter.login(USERNAME)

    assert first.value == "first-token"
    assert second.value == first.value
    assert second.expires_in == TOKEN_TIMEOUT_SECONDS
    assert await redis_client.get(adapter.keys.token(first.value)) == USERNAME.encode()
    session_raw = await redis_client.get(adapter.keys.session(USERNAME))
    assert session_raw is not None
    session = json.loads(session_raw)
    assert session["@class"] == (
        "cn.dev33.satoken.dao.SaSessionForJacksonCustomized"
    )
    assert session["loginId"] == USERNAME
    assert session["tokenSignList"] == [
        "java.util.Vector",
        [
            {
                "@class": "cn.dev33.satoken.session.TokenSign",
                "value": "first-token",
                "device": "default-device",
                "tag": None,
            }
        ],
    ]
    assert await redis_client.ttl(adapter.keys.token(first.value)) > 2_591_990
    assert await redis_client.ttl(adapter.keys.session(USERNAME)) > 2_591_990


@pytest.mark.integration
@pytest.mark.anyio
async def test_concurrent_login_calls_share_one_token(redis_client: Redis) -> None:
    counter = itertools.count(1)
    adapter = _adapter(redis_client, lambda: f"candidate-{next(counter)}")

    tokens = await asyncio.gather(*(adapter.login(USERNAME) for _ in range(8)))

    assert {token.value for token in tokens} == {"candidate-1"}


@pytest.mark.integration
@pytest.mark.anyio
async def test_logout_removes_satoken_keys_but_not_legacy_hash(
    redis_client: Redis,
) -> None:
    adapter = _adapter(redis_client)
    token = await adapter.login(USERNAME)
    legacy_key = f"xunzhi-agent:login:{USERNAME}"
    await cast(
        Awaitable[int],
        redis_client.hset(
            legacy_key, mapping={"legacy-token": "user-json"}
        ),
    )
    await redis_client.expire(legacy_key, 1800)

    await adapter.logout(token.value)

    assert await redis_client.exists(adapter.keys.token(token.value)) == 0
    assert await redis_client.exists(adapter.keys.session(USERNAME)) == 0
    assert await redis_client.exists(legacy_key) == 1
