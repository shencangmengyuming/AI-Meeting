import asyncio
from typing import Any

from app.interview.application.turn_compensation import TurnCompensationQueue


async def repair_turn_once(redis: Any, database: Any) -> bool:
    collection = database["interview_turn"]

    async def writer(turn: dict[str, Any]) -> None:
        existing = await collection.find_one(
            {
                "sessionId": turn.get("sessionId"),
                "requestId": turn.get("requestId"),
            }
        )
        if existing is None:
            await collection.insert_one(turn)

    return await TurnCompensationQueue(redis).process_one(writer)


async def run_turn_repair_worker(
    redis: Any,
    database: Any,
    stop_event: asyncio.Event,
    *,
    idle_seconds: float = 1.0,
) -> None:
    while not stop_event.is_set():
        try:
            processed = await repair_turn_once(redis, database)
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
