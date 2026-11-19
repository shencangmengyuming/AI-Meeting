import json
from datetime import datetime, timezone
from typing import Any, Protocol
from uuid import uuid4

from app.agent.infrastructure.configuration import AgentConfigurationRepository

AGENT_FILE_REPAIR_KEY = "agent:file:repair"


class AgentFileUploader(Protocol):
    async def upload(
        self,
        filename: str,
        content_type: str | None,
        content: bytes,
        configuration: Any,
    ) -> str: ...


class AgentFileRepository(Protocol):
    async def save(self, asset: dict[str, Any]) -> int: ...


class AgentSessionLookup(Protocol):
    async def bound_agent_id(self, session_id: str, user_id: int) -> int | None: ...


class AgentFileUploadService:
    def __init__(
        self,
        configurations: AgentConfigurationRepository,
        uploader: AgentFileUploader,
        repository: AgentFileRepository,
        redis: Any,
        *,
        sessions: AgentSessionLookup | None = None,
    ) -> None:
        self.configurations = configurations
        self.uploader = uploader
        self.repository = repository
        self.redis = redis
        self.sessions = sessions

    async def upload(
        self,
        *,
        username: str,
        user_id: int | None = None,
        session_id: str | None,
        biz_type: str | None,
        filename: str,
        content_type: str | None,
        content: bytes,
    ) -> dict[str, Any]:
        if not content:
            raise ValueError("uploaded file cannot be empty")
        normalized_session_id = session_id.strip() if session_id else None
        if normalized_session_id:
            if self.sessions is None or user_id is None:
                raise PermissionError("agent session ownership cannot be verified")
            agent_id = await self.sessions.bound_agent_id(
                normalized_session_id, user_id
            )
            if agent_id is None:
                raise LookupError("agent session has no bound Agent")
            configuration = await self.configurations.resolve_by_id(agent_id)
        else:
            configuration = await self.configurations.resolve(
                "GENERAL_AGENT_CHAT", aliases=("general", "通用智能体")
            )
        remote_url = await self.uploader.upload(
            filename, content_type, content, configuration
        )
        now = datetime.now(timezone.utc)
        normalized_name = filename.strip() or f"unknown_{int(now.timestamp())}"
        asset: dict[str, Any] = {
            "mutationId": str(uuid4()),
            "agentId": configuration.agent_id,
            "sessionId": normalized_session_id,
            "userName": username or "unknown",
            "bizType": biz_type or "general",
            "sourcePlatform": "xingchen",
            "fileName": normalized_name,
            "fileExt": _extension(normalized_name),
            "contentType": content_type,
            "fileSize": len(content),
            "fileUrl": remote_url,
            "uploadStatus": 1,
            "createTime": now,
            "updateTime": now,
            "delFlag": 0,
        }
        try:
            asset_id = await self.repository.save(asset)
        except Exception:
            await self.redis.lpush(
                AGENT_FILE_REPAIR_KEY,
                json.dumps({"asset": asset, "attempts": 0}, default=str),
            )
            raise
        return {"id": asset_id, **_response(asset)}


def _extension(filename: str) -> str | None:
    if "." not in filename or filename.endswith("."):
        return None
    return filename.rsplit(".", 1)[1].lower()


def _response(asset: dict[str, Any]) -> dict[str, Any]:
    return {
        key: asset[key]
        for key in (
            "sessionId",
            "bizType",
            "fileName",
            "fileSize",
            "contentType",
            "fileUrl",
            "createTime",
        )
    }
