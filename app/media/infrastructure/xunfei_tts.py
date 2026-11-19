import asyncio
from datetime import datetime, timezone
from email.utils import format_datetime
from typing import Any

import httpx

from app.media.infrastructure.tts import TtsSigner

TTS_CREATE_URL = "https://api.xf-yun.com/v1/private/dts_create"
TTS_QUERY_URL = "https://api.xf-yun.com/v1/private/dts_query"


class XunfeiTtsService:
    def __init__(
        self,
        app_id: str,
        api_key: str,
        api_secret: str,
        http: httpx.AsyncClient,
    ) -> None:
        self.app_id = app_id
        self.signer = TtsSigner(api_key, api_secret)
        self.http = http

    async def create_task(self, text: str) -> dict[str, object]:
        if not text or len(text) > 100000:
            raise ValueError("text length must be between 1 and 100000")
        payload = await self._post(
            TTS_CREATE_URL,
            {
                "header": {"app_id": self.app_id},
                "parameter": {"dts": {"vcn": "x4_lingxiaoxuan_oral"}},
                "payload": {"text": {"encoding": "utf8", "text": text}},
            },
        )
        task_id = _payload_value(payload, "task_id")
        if not isinstance(task_id, str) or not task_id:
            raise RuntimeError("TTS create response missing task id")
        return {"taskId": task_id}

    async def query_task(self, task_id: str) -> dict[str, object]:
        payload = await self._post(
            TTS_QUERY_URL,
            {"header": {"app_id": self.app_id, "task_id": task_id}},
        )
        status = int(_payload_value(payload, "task_status") or 0)
        result: dict[str, object] = {"taskId": task_id, "status": status}
        audio_url = _payload_value(payload, "audio_url")
        if isinstance(audio_url, str):
            result["audioUrl"] = audio_url
        return result

    async def wait_for_task(
        self,
        task_id: str,
        *,
        timeout_seconds: float = 60,
        poll_interval: float = 1,
    ) -> dict[str, object]:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout_seconds
        while loop.time() <= deadline:
            result = await self.query_task(task_id)
            raw_status = result["status"]
            if not isinstance(raw_status, (int, str)):
                raise RuntimeError("invalid TTS task status")
            status = int(raw_status)
            if status == 5:
                return result
            if status in {2, 4}:
                raise RuntimeError(f"TTS task failed with status {status}")
            await asyncio.sleep(max(poll_interval, 0))
        raise TimeoutError("TTS task polling timed out")

    async def _post(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        date = format_datetime(datetime.now(timezone.utc), usegmt=True)
        path = httpx.URL(url).path
        response = await self.http.post(
            url,
            headers={
                "Date": date,
                "Authorization": self.signer.sign("POST", path, date),
                "Content-Type": "application/json",
            },
            json=payload,
        )
        response.raise_for_status()
        root = response.json()
        if not isinstance(root, dict):
            raise RuntimeError("invalid TTS response")
        header = root.get("header")
        if isinstance(header, dict) and int(header.get("code", 0)) != 0:
            raise RuntimeError(f"TTS provider error: {header.get('code')}")
        return root


def _payload_value(root: dict[str, Any], key: str) -> Any:
    payload = root.get("payload")
    return payload.get(key) if isinstance(payload, dict) else None
