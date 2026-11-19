import json
from collections.abc import Awaitable, Callable
from typing import Any
from uuid import uuid4

TURN_COMPENSATION_KEY = "interview:turn:compensation"
TURN_COMPENSATION_FAILED_KEY = "interview:turn:compensation:failed"


class TurnCompensationQueue:
    def __init__(self, redis: Any, *, max_attempts: int = 3) -> None:
        self.redis = redis
        self.max_attempts = max(1, max_attempts)

    async def enqueue(self, turn: dict[str, Any], *, attempts: int = 0) -> None:
        request_id = str(turn.get("requestId") or "")
        payload = {
            "messageId": str(uuid4()),
            "mutationId": request_id,
            "sessionId": turn.get("sessionId"),
            "requestId": request_id,
            "seq": turn.get("seq"),
            "retryCount": attempts,
            "turn": turn,
        }
        await self.redis.lpush(TURN_COMPENSATION_KEY, json.dumps(payload, default=str))

    async def _requeue(self, payload: dict[str, Any]) -> None:
        await self.redis.lpush(
            TURN_COMPENSATION_KEY, json.dumps(payload, default=str)
        )

    async def process_one(
        self, writer: Callable[[dict[str, Any]], Awaitable[None]]
    ) -> bool:
        raw = await self.redis.rpop(TURN_COMPENSATION_KEY)
        if not raw:
            return False
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        payload = json.loads(raw)
        turn = payload.get("turn") or {}
        attempts = int(payload.get("retryCount", payload.get("attempts", 0)))
        try:
            await writer(turn)
        except Exception as exc:
            if attempts + 1 < self.max_attempts:
                payload["retryCount"] = attempts + 1
                payload["lastError"] = type(exc).__name__
                await self._requeue(payload)
            else:
                payload["retryCount"] = attempts + 1
                payload["lastError"] = type(exc).__name__
                await self.redis.lpush(
                    TURN_COMPENSATION_FAILED_KEY,
                    json.dumps(payload, default=str),
                )
            return False
        return True
