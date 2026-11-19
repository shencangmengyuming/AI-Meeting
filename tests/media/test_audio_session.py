import asyncio

import pytest


@pytest.mark.anyio
async def test_audio_session_has_bounded_queue_and_stop_signal() -> None:
    from app.media.application.audio_session import AudioSession

    session = AudioSession("s1", "u1", max_queue_size=1)
    await session.push(b"one")
    with pytest.raises(asyncio.QueueFull):
        await session.push(b"two")
    assert await session.receive() == b"one"
    await session.stop()
    assert session.stop_requested is True
