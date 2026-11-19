import pytest


@pytest.mark.anyio
async def test_asr_provider_streams_provider_frames_to_assembler() -> None:
    from app.media.infrastructure.asr import AsrProvider

    class WebSocketStub:
        async def send_bytes(self, frame: bytes) -> None:
            self.frame = frame

        async def __aiter__(self):
            yield {"segmentId": 1, "text": "hello", "final": False}
            yield {"segmentId": 1, "text": "hello world", "final": True}

        async def close(self) -> None:
            return None

    updates = [
        item
        async for item in AsrProvider(WebSocketStub()).transcribe([b"audio"])
    ]

    assert updates[-1].full_text == "hello world"
    assert updates[-1].committed_text == "hello world"
