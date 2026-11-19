import pytest


class RedisLockStub:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    async def set(self, key: str, value: str, *, nx: bool, ex: int) -> bool:
        if nx and key in self.values:
            return False
        self.values[key] = value
        return True

    async def eval(self, script: str, numkeys: int, key: str, token: str) -> int:
        if self.values.get(key) == token:
            del self.values[key]
            return 1
        return 0


@pytest.mark.anyio
async def test_heavy_lock_rejects_duplicate_stage_session() -> None:
    from app.interview.application.heavy_lock import HeavyTaskLock

    redis = RedisLockStub()
    first = HeavyTaskLock(redis, ttl_seconds=30)
    second = HeavyTaskLock(redis, ttl_seconds=30)

    async with first.acquire("resume", "session-1"):
        with pytest.raises(RuntimeError, match="already running"):
            async with second.acquire("resume", "session-1"):
                pass

    assert redis.values == {}
