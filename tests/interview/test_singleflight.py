import asyncio

import pytest


class RedisFlightStub:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    async def get(self, key: str):
        return self.values.get(key)

    async def set(
        self,
        key: str,
        value: str,
        *,
        nx: bool = False,
        ex: int | None = None,
    ) -> bool:
        if nx and key in self.values:
            return False
        self.values[key] = value
        return True

    async def delete(self, key: str) -> int:
        return int(self.values.pop(key, None) is not None)


@pytest.mark.anyio
async def test_singleflight_reuses_completed_result() -> None:
    from app.ai_runtime.application.singleflight import DistributedSingleFlight

    redis = RedisFlightStub()
    service = DistributedSingleFlight(redis, ttl_seconds=30)
    calls = 0

    async def supplier() -> dict[str, str]:
        nonlocal calls
        calls += 1
        return {"answer": "cached"}

    first = await service.execute("scoring", "request-1", supplier)
    second = await service.execute("scoring", "request-1", supplier)

    assert first.result == {"answer": "cached"}
    assert second.result == {"answer": "cached"}
    assert first.action == "OWNER_NEW"
    assert second.action == "REPLAY_SUCCESS"
    assert calls == 1


@pytest.mark.anyio
async def test_singleflight_concurrent_followers_do_not_duplicate_supplier() -> None:
    from app.ai_runtime.application.singleflight import DistributedSingleFlight

    redis = RedisFlightStub()
    service = DistributedSingleFlight(redis, ttl_seconds=30)
    calls = 0

    async def supplier() -> str:
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.01)
        return "answer"

    results = await asyncio.gather(
        service.execute("scoring", "request-2", supplier),
        service.execute("scoring", "request-2", supplier),
    )

    assert [item.result for item in results] == ["answer", "answer"]
    assert calls == 1
    assert {item.action for item in results} == {"OWNER_NEW", "FOLLOWER_WAIT"}


@pytest.mark.anyio
async def test_singleflight_failure_is_replayed_without_running_supplier_again(
) -> None:
    from app.ai_runtime.application.singleflight import DistributedSingleFlight

    redis = RedisFlightStub()
    service = DistributedSingleFlight(redis, ttl_seconds=30)
    calls = 0

    async def supplier() -> str:
        nonlocal calls
        calls += 1
        raise ValueError("provider failed")

    first = await service.execute("scoring", "request-3", supplier)
    second = await service.execute("scoring", "request-3", supplier)

    assert first.error == "provider failed"
    assert second.error == "provider failed"
    assert second.action == "REPLAY_FAILURE"
    assert calls == 1


@pytest.mark.anyio
async def test_singleflight_follower_on_another_instance_waits_for_owner() -> None:
    from app.ai_runtime.application.singleflight import DistributedSingleFlight

    redis = RedisFlightStub()
    owner = DistributedSingleFlight(redis, ttl_seconds=5)
    follower = DistributedSingleFlight(redis, ttl_seconds=5)
    release = asyncio.Event()

    async def slow() -> str:
        await release.wait()
        return "answer"

    owner_task = asyncio.create_task(owner.execute("score", "r3", slow))
    await asyncio.sleep(0)
    follower_task = asyncio.create_task(
        follower.execute("score", "r3", lambda: asyncio.sleep(0))
    )
    await asyncio.sleep(0.02)
    release.set()

    owner_result, follower_result = await asyncio.gather(owner_task, follower_task)
    assert owner_result.result == "answer"
    assert follower_result.action == "FOLLOWER_WAIT"
    assert follower_result.result == "answer"
