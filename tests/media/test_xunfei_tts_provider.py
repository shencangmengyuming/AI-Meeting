import httpx
import pytest

from app.media.infrastructure.xunfei_tts import XunfeiTtsService


@pytest.mark.anyio
async def test_tts_create_and_query_task() -> None:
    calls = []

    async def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if request.url.path.endswith("dts_create"):
            return httpx.Response(
                200,
                json={"header": {"code": 0}, "payload": {"task_id": "t1"}},
            )
        return httpx.Response(
            200,
            json={
                "header": {"code": 0},
                "payload": {
                    "task_status": "5",
                    "audio_url": "https://api.xf-yun.com/a.mp3",
                },
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        service = XunfeiTtsService("app", "key", "secret", client)
        created = await service.create_task("hello")
        queried = await service.query_task("t1")

    assert created["taskId"] == "t1"
    assert queried == {"taskId": "t1", "status": 5, "audioUrl": "https://api.xf-yun.com/a.mp3"}
    assert len(calls) == 2


@pytest.mark.anyio
async def test_tts_polling_stops_on_failure_status() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"header": {"code": 0}, "payload": {"task_status": "4"}},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        service = XunfeiTtsService("app", "key", "secret", client)
        with pytest.raises(RuntimeError, match="TTS task failed"):
            await service.wait_for_task("t1", timeout_seconds=0.1, poll_interval=0)
