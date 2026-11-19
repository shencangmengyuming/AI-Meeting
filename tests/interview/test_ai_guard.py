import asyncio

import pytest


@pytest.mark.anyio
async def test_ai_guard_retries_transient_failure_and_returns_result() -> None:
    from app.interview.application.ai_guard import AiCallGuard

    attempts = 0

    async def operation() -> str:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise TimeoutError("temporary")
        return "ok"

    result = await AiCallGuard(
        timeout_seconds=1,
        max_retries=2,
        retryable=(TimeoutError,),
    ).execute("scoring", operation)

    assert result == "ok"
    assert attempts == 3


@pytest.mark.anyio
async def test_ai_guard_rejects_operation_that_exceeds_timeout() -> None:
    from app.interview.application.ai_guard import AiCallGuard

    async def operation() -> str:
        await asyncio.sleep(0.05)
        return "late"

    with pytest.raises(TimeoutError):
        await AiCallGuard(timeout_seconds=0.001, max_retries=0).execute(
            "scoring", operation
        )


@pytest.mark.anyio
async def test_ai_guard_limits_parallel_calls_per_stage() -> None:
    from app.interview.application.ai_guard import AiCallGuard

    active = 0
    maximum = 0

    async def operation() -> str:
        nonlocal active, maximum
        active += 1
        maximum = max(maximum, active)
        await asyncio.sleep(0.01)
        active -= 1
        return "ok"

    guard = AiCallGuard(timeout_seconds=1, max_concurrency_by_stage={"scoring": 1})
    results = await asyncio.gather(
        guard.execute("scoring", operation),
        guard.execute("scoring", operation),
    )

    assert results == ["ok", "ok"]
    assert maximum == 1


@pytest.mark.anyio
async def test_ai_guard_opens_circuit_and_allows_half_open_probe() -> None:
    from app.interview.application.ai_guard import AiCallGuard, CircuitOpenError

    attempts = 0

    async def failing() -> str:
        nonlocal attempts
        attempts += 1
        raise TimeoutError("provider down")

    guard = AiCallGuard(
        timeout_seconds=1,
        max_retries=0,
        retryable=(TimeoutError,),
        circuit_failure_threshold=2,
        circuit_reset_seconds=0.01,
    )

    with pytest.raises(TimeoutError):
        await guard.execute("scoring", failing)
    with pytest.raises(TimeoutError):
        await guard.execute("scoring", failing)
    with pytest.raises(CircuitOpenError):
        await guard.execute("scoring", failing)
    assert attempts == 2

    await asyncio.sleep(0.02)

    async def recovered() -> str:
        return "ok"

    assert await guard.execute("scoring", recovered) == "ok"
    assert await guard.execute("scoring", recovered) == "ok"


@pytest.mark.anyio
async def test_ai_guard_cancellation_releases_stage_capacity() -> None:
    from app.interview.application.ai_guard import AiCallGuard

    started = asyncio.Event()

    async def blocked() -> str:
        started.set()
        await asyncio.Event().wait()
        return "never"

    guard = AiCallGuard(timeout_seconds=10, max_concurrency_by_stage={"score": 1})
    task = asyncio.create_task(guard.execute("score", blocked))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert await guard.execute("score", lambda: asyncio.sleep(0, result="ok")) == "ok"
