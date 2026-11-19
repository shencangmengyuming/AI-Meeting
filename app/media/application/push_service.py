import asyncio
import json
from typing import Any

from app.media.application.connection_registry import ConnectionRegistry
from app.media.infrastructure.websocket_routing import WebSocketRouting


class WebSocketPushService:
    def __init__(
        self,
        registry: ConnectionRegistry,
        routing: WebSocketRouting,
    ) -> None:
        self.registry = registry
        self.routing = routing

    async def push(self, user_id: str, envelope: dict[str, Any]) -> int:
        delivered = await self.registry.push(user_id, envelope)
        if delivered:
            return delivered
        return await self.routing.publish(user_id, envelope)

    async def consume(self, pubsub: Any, stop_event: asyncio.Event) -> None:
        async for message in pubsub.listen():
            if stop_event.is_set():
                return
            if message.get("type") != "message":
                continue
            raw = message.get("data")
            if isinstance(raw, bytes):
                raw = raw.decode()
            payload = json.loads(raw)
            await self.registry.push(
                str(payload["userId"]), dict(payload["envelope"])
            )
