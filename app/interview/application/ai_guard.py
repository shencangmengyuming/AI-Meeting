import asyncio
from collections.abc import Awaitable, Callable, Mapping
from typing import TypeVar

T = TypeVar("T")


class CircuitOpenError(RuntimeError):
    pass


class AiCallGuard:
    def __init__(
        self,
        *,
        timeout_seconds: float = 30.0,
        max_retries: int = 0,
        retryable: tuple[type[BaseException], ...] = (TimeoutError,),
        max_concurrency_by_stage: Mapping[str, int] | None = None,
        circuit_failure_threshold: int = 5,
        circuit_reset_seconds: float = 30.0,
    ) -> None:
        self.timeout_seconds = max(timeout_seconds, 0.001)
        self.max_retries = max(max_retries, 0)
        self.retryable = retryable
        self.circuit_failure_threshold = max(circuit_failure_threshold, 1)
        self.circuit_reset_seconds = max(circuit_reset_seconds, 0.001)
        self._semaphores = {
            stage: asyncio.Semaphore(max(limit, 1))
            for stage, limit in (max_concurrency_by_stage or {}).items()
        }
        self._circuit_locks: dict[str, asyncio.Lock] = {}
        self._circuit_failures: dict[str, int] = {}
        self._circuit_opened_at: dict[str, float] = {}
        self._half_open: set[str] = set()

    async def execute(
        self,
        stage: str,
        operation: Callable[[], Awaitable[T]],
    ) -> T:
        semaphore = self._semaphores.get(stage)
        if semaphore is None:
            semaphore = self._semaphores.setdefault(stage, asyncio.Semaphore(1))
        async with semaphore:
            await self._before_call(stage)
            try:
                for attempt in range(self.max_retries + 1):
                    try:
                        result = await asyncio.wait_for(
                            operation(), timeout=self.timeout_seconds
                        )
                        await self._record_success(stage)
                        return result
                    except self.retryable:
                        if attempt >= self.max_retries:
                            raise
            except asyncio.CancelledError:
                await self._cancel_probe(stage)
                raise
            except BaseException:
                await self._record_failure(stage)
                raise
        raise RuntimeError("AI guard exhausted without returning")

    async def _before_call(self, stage: str) -> None:
        lock = self._circuit_locks.setdefault(stage, asyncio.Lock())
        async with lock:
            opened_at = self._circuit_opened_at.get(stage)
            if opened_at is None:
                return
            elapsed = asyncio.get_running_loop().time() - opened_at
            if elapsed < self.circuit_reset_seconds or stage in self._half_open:
                raise CircuitOpenError(f"AI circuit is open for stage: {stage}")
            self._half_open.add(stage)

    async def _record_success(self, stage: str) -> None:
        lock = self._circuit_locks.setdefault(stage, asyncio.Lock())
        async with lock:
            self._circuit_failures.pop(stage, None)
            self._circuit_opened_at.pop(stage, None)
            self._half_open.discard(stage)

    async def _record_failure(self, stage: str) -> None:
        lock = self._circuit_locks.setdefault(stage, asyncio.Lock())
        async with lock:
            failures = self._circuit_failures.get(stage, 0) + 1
            self._circuit_failures[stage] = failures
            self._half_open.discard(stage)
            if failures >= self.circuit_failure_threshold:
                self._circuit_opened_at[stage] = asyncio.get_running_loop().time()

    async def _cancel_probe(self, stage: str) -> None:
        lock = self._circuit_locks.setdefault(stage, asyncio.Lock())
        async with lock:
            self._half_open.discard(stage)
