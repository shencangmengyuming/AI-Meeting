import asyncio
import json
from collections.abc import AsyncIterator, Awaitable, Callable, Iterable
from typing import Any

from app.media.domain.transcription import (
    AstTranscriptionAssembler,
    TranscriptionUpdate,
)


class AsrProvider:
    def __init__(self, websocket: Any) -> None:
        self.websocket = websocket

    async def transcribe(
        self, frames: Iterable[bytes]
    ) -> AsyncIterator[TranscriptionUpdate]:
        for frame in frames:
            await self.websocket.send_bytes(frame)
        assembler = AstTranscriptionAssembler()
        async for payload in self.websocket:
            yield assembler.apply(
                segment_id=int(payload.get("segmentId", 0)),
                text=str(payload.get("text") or ""),
                finalized=bool(payload.get("final")),
            )

    async def close(self) -> None:
        await self.websocket.close()


class XunfeiAsrProvider:
    """Structured sender/receiver loop around a connected Xunfei WebSocket."""

    def __init__(
        self,
        websocket_factory: Callable[[], Awaitable[Any]],
        *,
        frame_interval_seconds: float = 0.04,
    ) -> None:
        self.websocket_factory = websocket_factory
        self.frame_interval_seconds = max(frame_interval_seconds, 0)

    async def run(
        self,
        audio_queue: asyncio.Queue[bytes | None],
        update_sink: Callable[[TranscriptionUpdate], Awaitable[None]],
        stop_event: asyncio.Event,
    ) -> None:
        websocket = await self.websocket_factory()
        assembler = AstTranscriptionAssembler()

        async def sender() -> None:
            while not stop_event.is_set():
                frame = await audio_queue.get()
                if frame is None:
                    await websocket.send(json.dumps({"end": True}))
                    return
                await websocket.send(frame)
                if self.frame_interval_seconds:
                    await asyncio.sleep(self.frame_interval_seconds)

        async def receiver() -> None:
            async for raw in websocket:
                payload = json.loads(raw) if isinstance(raw, str) else raw
                packet = _ast_packet(payload)
                update = assembler.apply(
                    segment_id=packet["segmentId"],
                    text=packet["text"],
                    finalized=packet["final"],
                    pgs=packet["pgs"],
                    rg=packet["rg"],
                    bg=packet["bg"],
                    ed=packet["ed"],
                )
                await update_sink(update)
                if packet["final"]:
                    stop_event.set()
                    return

        try:
            async with asyncio.TaskGroup() as group:
                group.create_task(sender())
                group.create_task(receiver())
        finally:
            await websocket.close()


def _ast_packet(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("ASR packet is not an object")
    data = payload.get("data")
    data = data if isinstance(data, dict) else payload
    result = data.get("result")
    result = result if isinstance(result, dict) else data
    text = result.get("text")
    if not isinstance(text, str):
        words = result.get("ws")
        if isinstance(words, list):
            text = "".join(
                str(candidate.get("w") or "")
                for item in words
                if isinstance(item, dict)
                for candidate in item.get("cw", [])
                if isinstance(candidate, dict)
            )
        else:
            text = ""
    return {
        "segmentId": int(result.get("sn", result.get("segmentId", 0))),
        "text": text,
        "final": bool(data.get("ls") or result.get("ls") or payload.get("final")),
        "pgs": result.get("pgs") or data.get("pgs"),
        "rg": _range(result.get("rg") or data.get("rg")),
        "bg": _optional_int(result.get("bg", data.get("bg"))),
        "ed": _optional_int(result.get("ed", data.get("ed"))),
    }


def _optional_int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _range(value: Any) -> tuple[int, int] | None:
    if not isinstance(value, (list, tuple)) or len(value) < 2:
        return None
    start, end = _optional_int(value[0]), _optional_int(value[1])
    return (start, end) if start is not None and end is not None else None
