import asyncio
from collections import defaultdict
from typing import Any


class ConnectionRegistry:
    def __init__(self) -> None:
        self._connections: dict[str, dict[str, Any]] = defaultdict(dict)
        self._lock = asyncio.Lock()

    async def add(self, user_id: str, connection_id: str, websocket: Any) -> None:
        async with self._lock:
            self._connections[user_id][connection_id] = websocket

    async def remove(self, user_id: str, connection_id: str) -> None:
        async with self._lock:
            connections = self._connections.get(user_id)
            if connections is None:
                return
            connections.pop(connection_id, None)
            if not connections:
                self._connections.pop(user_id, None)

    async def is_online(self, user_id: str) -> bool:
        async with self._lock:
            return bool(self._connections.get(user_id))

    async def push(self, user_id: str, envelope: dict[str, Any]) -> int:
        async with self._lock:
            sockets = list(self._connections.get(user_id, {}).values())
        delivered = 0
        for socket in sockets:
            try:
                await socket.send_json(envelope)
            except Exception:
                continue
            delivered += 1
        return delivered
