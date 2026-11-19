import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

RELEASE_LOCK_SCRIPT = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('DEL', KEYS[1])
end
return 0
"""


class HeavyTaskLock:
    def __init__(self, redis: Any, *, ttl_seconds: int = 60) -> None:
        self.redis = redis
        self.ttl_seconds = max(ttl_seconds, 1)

    @asynccontextmanager
    async def acquire(self, stage: str, session_id: str) -> AsyncIterator[None]:
        key = f"interview:ai:heavy:lock:{stage}:{session_id}"
        token = secrets.token_urlsafe(16)
        acquired = await self.redis.set(
            key,
            token,
            nx=True,
            ex=self.ttl_seconds,
        )
        if not acquired:
            raise RuntimeError("heavy task already running")
        try:
            yield
        finally:
            await self.redis.eval(RELEASE_LOCK_SCRIPT, 1, key, token)
