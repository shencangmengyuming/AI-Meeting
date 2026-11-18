from collections.abc import Awaitable
from typing import Any, cast

from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth_user.domain.session import AuthIdentity


class MySqlAuthIdentityLookup:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        redis: Redis,
        *,
        cache_ttl_seconds: int = 1800,
    ) -> None:
        self.session_factory = session_factory
        self.redis = redis
        self.cache_ttl_seconds = cache_ttl_seconds

    async def find_by_username(self, username: str) -> AuthIdentity | None:
        if not username:
            return None
        cache_key = f"xunzhi:user:id:{username}"
        cached_user_id = await self.redis.get(cache_key)
        user_id = _parse_user_id(cached_user_id)

        async with self.session_factory() as session:
            if user_id is None:
                user_id = await session.scalar(
                    text(
                        "SELECT id FROM t_user "
                        "WHERE username = :username AND del_flag = 0 LIMIT 1"
                    ),
                    {"username": username},
                )
                if user_id is None:
                    return None
                user_id = int(user_id)
                await cast(
                    Awaitable[Any],
                    self.redis.set(
                        cache_key,
                        str(user_id),
                        ex=self.cache_ttl_seconds,
                    ),
                )

            is_admin = await session.scalar(
                text(
                    "SELECT EXISTS("
                    "SELECT 1 FROM admin_permission "
                    "WHERE username = :username "
                    "AND is_admin = 1 AND del_flag = 0"
                    ")"
                ),
                {"username": username},
            )

        roles = {"user"}
        if bool(is_admin):
            roles.add("admin")
        return AuthIdentity(
            user_id=user_id,
            username=username,
            roles=frozenset(roles),
        )


def _parse_user_id(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
