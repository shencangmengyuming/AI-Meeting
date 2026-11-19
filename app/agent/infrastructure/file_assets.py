from typing import Any

import httpx
from sqlalchemy import text

from app.agent.domain.configuration import AgentConfiguration

XUNFEI_UPLOAD_URL = "https://xingchen-api.xf-yun.com/workflow/v1/upload_file"


class XunfeiAgentFileUploader:
    def __init__(self, http: httpx.AsyncClient) -> None:
        self.http = http

    async def upload(
        self,
        filename: str,
        content_type: str | None,
        content: bytes,
        configuration: AgentConfiguration,
    ) -> str:
        response = await self.http.post(
            XUNFEI_UPLOAD_URL,
            headers={
                "Authorization": (
                    f"Bearer {configuration.api_key}:{configuration.api_secret}"
                )
            },
            files={
                "file": (
                    filename,
                    content,
                    content_type or "application/octet-stream",
                )
            },
        )
        response.raise_for_status()
        payload = response.json()
        url = _find_url(payload)
        if url is None:
            raise RuntimeError("Xunfei upload response missing file URL")
        return url


class MySqlAgentFileRepository:
    def __init__(self, session_factory: Any) -> None:
        self.session_factory = session_factory

    async def save(self, asset: dict[str, Any]) -> int:
        async with self.session_factory() as session:
            result = await session.execute(
                text(
                    "INSERT INTO agent_file_asset "
                    "(agent_id,session_id,user_name,biz_type,source_platform,"
                    "file_name,file_ext,content_type,file_size,file_url,"
                    "upload_status,create_time,update_time,del_flag) VALUES "
                    "(:agentId,:sessionId,:userName,:bizType,:sourcePlatform,"
                    ":fileName,:fileExt,:contentType,:fileSize,:fileUrl,"
                    ":uploadStatus,:createTime,:updateTime,:delFlag)"
                ),
                asset,
            )
            await session.commit()
            inserted_id = getattr(result, "lastrowid", None)
        if inserted_id is None:
            raise RuntimeError("persist uploaded file URL failed")
        return int(inserted_id)


def _find_url(payload: Any) -> str | None:
    if isinstance(payload, str) and payload.startswith("http"):
        return payload
    if not isinstance(payload, dict):
        return None
    for key in ("url", "file_url", "fileUrl"):
        value = payload.get(key)
        if isinstance(value, str) and value.startswith("http"):
            return value
    for value in payload.values():
        found = _find_url(value)
        if found:
            return found
    return None
