import asyncio
import dataclasses
import json
import secrets
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Generic, TypeVar

T = TypeVar("T")

ACQUIRE_SCRIPT = """
-- singleflight_acquire_v1
local raw = redis.call('GET', KEYS[1])
local now = tonumber(ARGV[2])
local ttl = tonumber(ARGV[3])
local stale = tonumber(ARGV[4])
if not raw then
  local state = {status='RUNNING', owner=ARGV[1], fencing=1, heartbeat=now}
  redis.call('SET', KEYS[1], cjson.encode(state), 'EX', ttl)
  return cjson.encode({action='OWNER_NEW', state=state})
end
local state = cjson.decode(raw)
if state.status == 'SUCCEEDED' then
  return cjson.encode({action='REPLAY_SUCCESS', state=state})
end
if state.status == 'FAILED' then
  return cjson.encode({action='REPLAY_FAILURE', state=state})
end
if state.status == 'RUNNING' and now - tonumber(state.heartbeat or 0) > stale then
  state.owner = ARGV[1]
  state.fencing = tonumber(state.fencing or 0) + 1
  state.heartbeat = now
  redis.call('SET', KEYS[1], cjson.encode(state), 'EX', ttl)
  return cjson.encode({action='OWNER_TAKEOVER', state=state})
end
return cjson.encode({action='FOLLOWER_WAIT', state=state})
"""

OWNER_WRITE_SCRIPT = """
-- singleflight_owner_write_v1
local raw = redis.call('GET', KEYS[1])
if not raw then return 0 end
local state = cjson.decode(raw)
if state.status ~= 'RUNNING' or state.owner ~= ARGV[1]
   or tonumber(state.fencing or 0) ~= tonumber(ARGV[2]) then
  return 0
end
redis.call('SET', KEYS[1], ARGV[3], 'EX', tonumber(ARGV[4]))
return 1
"""

HEARTBEAT_SCRIPT = """
-- singleflight_heartbeat_v1
local raw = redis.call('GET', KEYS[1])
if not raw then return 0 end
local state = cjson.decode(raw)
if state.status ~= 'RUNNING' or state.owner ~= ARGV[1]
   or tonumber(state.fencing or 0) ~= tonumber(ARGV[2]) then
  return 0
end
state.heartbeat = tonumber(ARGV[3])
redis.call('SET', KEYS[1], cjson.encode(state), 'EX', tonumber(ARGV[4]))
return 1
"""


@dataclass(frozen=True)
class SingleFlightResult(Generic[T]):
    action: str
    result: T | None = None
    error: str | None = None


class DistributedSingleFlight:
    def __init__(
        self,
        redis: Any,
        *,
        ttl_seconds: int = 60,
        follower_poll_seconds: float = 0.01,
    ) -> None:
        self.redis = redis
        self.ttl_seconds = max(ttl_seconds, 1)
        self._local_waiters: dict[str, asyncio.Future[SingleFlightResult[Any]]] = {}
        self.follower_poll_seconds = max(follower_poll_seconds, 0.001)

    async def execute(
        self,
        stage: str,
        request_key: str,
        supplier: Callable[[], Awaitable[T]],
    ) -> SingleFlightResult[T]:
        key = f"ai:flight:{stage}:{request_key}"
        if hasattr(self.redis, "eval"):
            return await self._execute_atomic(key, supplier)
        waiter = self._local_waiters.get(key)
        if waiter is not None:
            result = await waiter
            return SingleFlightResult(
                action="FOLLOWER_WAIT",
                result=result.result,
                error=result.error,
            )

        raw = await self.redis.get(key)
        if raw:
            payload = self._payload(raw)
            if payload.get("status") != "RUNNING":
                return self._decode(raw, "REPLAY_SUCCESS")
            waiter = self._local_waiters.get(key)
            if waiter is not None:
                result = await waiter
                return SingleFlightResult(
                    action="FOLLOWER_WAIT",
                    result=result.result,
                    error=result.error,
                )

        owner_token = secrets.token_urlsafe(16)
        claimed = await self.redis.set(
            key,
            json.dumps({"status": "RUNNING", "owner": owner_token}),
            nx=True,
            ex=self.ttl_seconds,
        )
        if not claimed:
            raw = await self.redis.get(key)
            if raw:
                if self._payload(raw).get("status") != "RUNNING":
                    return self._decode(raw, "REPLAY_SUCCESS")
                waiter = self._local_waiters.get(key)
                if waiter is not None:
                    result = await waiter
                    return SingleFlightResult(
                        action="FOLLOWER_WAIT",
                        result=result.result,
                        error=result.error,
                    )
            return await self._wait_for_owner(key)

        future: asyncio.Future[SingleFlightResult[Any]] = (
            asyncio.get_running_loop().create_future()
        )
        self._local_waiters[key] = future
        try:
            try:
                result = await supplier()
            except Exception as exc:
                failure = SingleFlightResult[T](
                    action="OWNER_NEW",
                    error=str(exc),
                )
                await self.redis.set(
                    key,
                    json.dumps(
                        {
                            "status": "FAILED",
                            "owner": owner_token,
                            "error": str(exc),
                        }
                    ),
                    ex=self.ttl_seconds,
                )
                future.set_result(failure)
                return failure

            success = SingleFlightResult[T](action="OWNER_NEW", result=result)
            await self.redis.set(
                key,
                json.dumps(
                    {"status": "SUCCEEDED", "owner": owner_token, "result": result},
                    default=_json_default,
                ),
                ex=self.ttl_seconds,
            )
            future.set_result(success)
            return success
        finally:
            self._local_waiters.pop(key, None)

    async def _wait_for_owner(self, key: str) -> SingleFlightResult[Any]:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.ttl_seconds
        while loop.time() < deadline:
            await asyncio.sleep(self.follower_poll_seconds)
            raw = await self.redis.get(key)
            if not raw:
                break
            if self._payload(raw).get("status") != "RUNNING":
                replay = self._decode(raw, "REPLAY_SUCCESS")
                return SingleFlightResult(
                    action="FOLLOWER_WAIT",
                    result=replay.result,
                    error=replay.error,
                )
        return SingleFlightResult(
            action="FOLLOWER_WAIT",
            error="single-flight owner did not complete before timeout",
        )

    async def _execute_atomic(
        self,
        key: str,
        supplier: Callable[[], Awaitable[T]],
    ) -> SingleFlightResult[T]:
        owner_token = secrets.token_urlsafe(16)
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.ttl_seconds * 2
        while loop.time() < deadline:
            decision_raw = await self.redis.eval(
                ACQUIRE_SCRIPT,
                1,
                key,
                owner_token,
                int(loop.time() * 1000),
                self.ttl_seconds,
                self.ttl_seconds * 1000,
            )
            decision = self._payload(decision_raw)
            action = str(decision.get("action") or "")
            state = decision.get("state")
            state = state if isinstance(state, dict) else {}
            if action == "REPLAY_SUCCESS":
                return SingleFlightResult(action=action, result=state.get("result"))
            if action == "REPLAY_FAILURE":
                return SingleFlightResult(
                    action=action,
                    error=str(state.get("error") or "single-flight failed"),
                )
            if action in {"OWNER_NEW", "OWNER_TAKEOVER"}:
                fencing = int(state.get("fencing", 0))
                return await self._run_atomic_owner(
                    key, owner_token, fencing, action, supplier
                )
            await asyncio.sleep(self.follower_poll_seconds)
        return SingleFlightResult(
            action="FOLLOWER_WAIT",
            error="single-flight owner did not complete before timeout",
        )

    async def _run_atomic_owner(
        self,
        key: str,
        owner_token: str,
        fencing: int,
        action: str,
        supplier: Callable[[], Awaitable[T]],
    ) -> SingleFlightResult[T]:
        heartbeat = asyncio.create_task(
            self._heartbeat(key, owner_token, fencing)
        )
        try:
            try:
                result = await supplier()
            except Exception as exc:
                payload = json.dumps(
                    {
                        "status": "FAILED",
                        "owner": owner_token,
                        "fencing": fencing,
                        "error": str(exc),
                    }
                )
                written = await self._owner_write(
                    key, owner_token, fencing, payload
                )
                if not written:
                    return SingleFlightResult(
                        action=action,
                        error="single-flight owner lost fencing token",
                    )
                return SingleFlightResult(action=action, error=str(exc))
            payload = json.dumps(
                {
                    "status": "SUCCEEDED",
                    "owner": owner_token,
                    "fencing": fencing,
                    "result": result,
                },
                default=_json_default,
            )
            written = await self._owner_write(key, owner_token, fencing, payload)
            if not written:
                return SingleFlightResult(
                    action=action,
                    error="single-flight owner lost fencing token",
                )
            return SingleFlightResult(action=action, result=result)
        finally:
            heartbeat.cancel()
            await asyncio.gather(heartbeat, return_exceptions=True)

    async def _heartbeat(
        self, key: str, owner_token: str, fencing: int
    ) -> None:
        interval = max(self.ttl_seconds / 3, 0.1)
        loop = asyncio.get_running_loop()
        while True:
            await asyncio.sleep(interval)
            alive = await self.redis.eval(
                HEARTBEAT_SCRIPT,
                1,
                key,
                owner_token,
                fencing,
                int(loop.time() * 1000),
                self.ttl_seconds,
            )
            if not alive:
                return

    async def _owner_write(
        self, key: str, owner_token: str, fencing: int, payload: str
    ) -> bool:
        return bool(
            await self.redis.eval(
                OWNER_WRITE_SCRIPT,
                1,
                key,
                owner_token,
                fencing,
                payload,
                self.ttl_seconds,
            )
        )

    @staticmethod
    def _payload(raw: Any) -> dict[str, Any]:
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        payload = json.loads(raw) if isinstance(raw, str) else raw
        return payload if isinstance(payload, dict) else {}

    @staticmethod
    def _decode(raw: Any, replay_action: str) -> SingleFlightResult[Any]:
        payload = DistributedSingleFlight._payload(raw)
        if payload.get("status") == "FAILED":
            return SingleFlightResult(
                action="REPLAY_FAILURE",
                error=str(payload.get("error") or "single-flight failed"),
            )
        if payload.get("status") == "SUCCEEDED":
            return SingleFlightResult(
                action=replay_action,
                result=payload.get("result"),
            )
        raise RuntimeError("single-flight request is still running")


def _json_default(value: Any) -> Any:
    if dataclasses.is_dataclass(value):
        return dataclasses.asdict(value)  # type: ignore[arg-type]
    raise TypeError(f"unsupported single-flight result: {type(value).__name__}")
