import asyncio
import json
from typing import Any

from app.agent.application.files import AGENT_FILE_REPAIR_KEY


async def repair_one(redis: Any, repository: Any, *, max_attempts: int = 3) -> bool:
    raw = await redis.rpop(AGENT_FILE_REPAIR_KEY)
    if not raw:
        return False
    if isinstance(raw, bytes):
        raw = raw.decode()
    payload = json.loads(raw)
    attempts = int(payload.get("attempts", 0))
    try:
        await repository.save(payload["asset"])
    except Exception:
        if attempts + 1 < max_attempts:
            payload["attempts"] = attempts + 1
            await redis.lpush(AGENT_FILE_REPAIR_KEY, json.dumps(payload))
        return False
    return True


async def run_agent_file_repair_worker(
    redis: Any,
    repository: Any,
    stop_event: asyncio.Event,
    *,
    idle_seconds: float = 1.0,
) -> None:
    while not stop_event.is_set():
        try:
            processed = await repair_one(redis, repository)
        except asyncio.CancelledError:
            raise
        except Exception:
            processed = False
        if processed:
            continue
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=idle_seconds)
        except TimeoutError:
            pass
