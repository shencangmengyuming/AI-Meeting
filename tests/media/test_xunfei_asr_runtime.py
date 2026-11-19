import asyncio
import json

import pytest

from app.media.infrastructure.asr import XunfeiAsrProvider


class Socket:
    def __init__(self) -> None:
        self.sent = []
        self.closed = False
        self.responses = [
            json.dumps({"data": {"result": {"sn": 1, "text": "hello"}}}),
            json.dumps({"data": {"ls": True, "result": {"sn": 2, "text": "."}}}),
        ]

    async def send(self, value):
        self.sent.append(json.loads(value) if isinstance(value, str) else value)

    async def close(self):
        self.closed = True

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self.responses:
            raise StopAsyncIteration
        return self.responses.pop(0)


@pytest.mark.anyio
async def test_xunfei_asr_runs_sender_receiver_and_closes_socket() -> None:
    socket = Socket()
    queue = asyncio.Queue()
    await queue.put(b"audio")
    await queue.put(None)
    updates = []

    async def factory():
        return socket

    async def sink(update):
        updates.append(update)

    await XunfeiAsrProvider(factory, frame_interval_seconds=0).run(
        queue, sink, asyncio.Event()
    )

    assert socket.sent[0] == b"audio"
    assert socket.sent[-1]["end"] is True
    assert updates[-1].full_text == "hello."
    assert socket.closed is True


@pytest.mark.anyio
async def test_xunfei_asr_preserves_ast_merge_metadata() -> None:
    socket = Socket()
    socket.responses = [
        json.dumps(
            {"data": {"result": {"sn": 1, "bg": 0, "ed": 1200, "text": "我今天"}}}
        ),
        json.dumps(
            {"data": {"result": {"sn": 2, "bg": 1200, "ed": 2100, "text": "聊一下"}}}
        ),
        json.dumps(
            {"data": {"result": {"sn": 3, "bg": 2100, "ed": 3400, "text": "实时转写"}}}
        ),
        json.dumps(
            {
                "data": {
                    "ls": True,
                    "result": {
                        "sn": 4,
                        "bg": 1200,
                        "ed": 3400,
                        "text": "聊一下实时转写",
                    },
                }
            }
        ),
    ]
    queue = asyncio.Queue()
    await queue.put(None)
    updates = []

    async def factory():
        return socket

    async def sink(update):
        updates.append(update)

    await XunfeiAsrProvider(factory, frame_interval_seconds=0).run(
        queue, sink, asyncio.Event()
    )

    assert updates[-1].full_text == "我今天聊一下实时转写"
