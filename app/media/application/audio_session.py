import asyncio


class AudioSession:
    def __init__(
        self, session_id: str, user_id: str, *, max_queue_size: int = 32
    ) -> None:
        self.session_id = session_id
        self.user_id = user_id
        self.queue: asyncio.Queue[bytes | None] = asyncio.Queue(
            maxsize=max_queue_size
        )
        self.stop_requested = False

    async def push(self, frame: bytes) -> None:
        self.queue.put_nowait(frame)

    async def receive(self) -> bytes | None:
        return await self.queue.get()

    async def stop(self) -> None:
        if self.stop_requested:
            return
        self.stop_requested = True
        await self.queue.put(None)
