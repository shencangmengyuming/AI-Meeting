import inspect
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.agent.domain.session import AgentSession


class AgentSessionService:
    def __init__(self, database) -> None:
        self.sessions = database["agent_conversation"]
        self.messages = database["agent_message"]

    async def create_session(
        self,
        user_id: int,
        title: str | None = None,
        *,
        agent_id: int | None = None,
        first_message: str | None = None,
    ) -> AgentSession:
        resolved_title = title or _title(first_message)
        session = AgentSession(str(uuid4()), user_id, resolved_title, agent_id)
        await self.sessions.insert_one(
            {
                "sessionId": session.session_id,
                "userId": user_id,
                "agentId": agent_id,
                "title": resolved_title,
                "conversationTitle": resolved_title,
                "messageCount": 0,
                "totalTokens": 0,
                "status": 1,
                "delFlag": 0,
                "createTime": datetime.now(timezone.utc),
            }
        )
        return session

    async def append_message(
        self,
        session_id: str,
        user_id: int,
        role: str,
        content: str,
    ) -> None:
        await self._require_owned(session_id, user_id)
        await self.messages.insert_one(
            {
                "sessionId": session_id,
                "userId": user_id,
                "role": role,
                "content": content,
                "delFlag": 0,
                "createTime": datetime.now(timezone.utc),
            }
        )

    async def list_messages(
        self, session_id: str, user_id: int
    ) -> list[dict[str, object]]:
        await self._require_owned(session_id, user_id)
        documents = await _find_many(
            self.messages,
            {"sessionId": session_id, "userId": user_id, "delFlag": 0},
        )
        documents.sort(key=lambda item: item.get("createTime") or "")
        return documents

    async def list_sessions(self, user_id: int) -> list[dict[str, object]]:
        documents = await _find_many(
            self.sessions, {"userId": user_id, "delFlag": 0}
        )
        documents.sort(key=lambda item: item.get("createTime") or "", reverse=True)
        return documents

    async def page_sessions(
        self,
        user_id: int,
        *,
        current: int = 1,
        size: int = 10,
        status: int | None = None,
        keyword: str | None = None,
    ) -> dict[str, Any]:
        documents = await self.list_sessions(user_id)
        if status is not None:
            documents = [item for item in documents if item.get("status") == status]
        normalized_keyword = (keyword or "").strip().lower()
        if normalized_keyword:
            documents = [
                item
                for item in documents
                if normalized_keyword
                in str(item.get("conversationTitle") or item.get("title") or "").lower()
            ]
        resolved_current = max(current, 1)
        resolved_size = min(max(size, 1), 100)
        start = (resolved_current - 1) * resolved_size
        return {
            "records": documents[start : start + resolved_size],
            "current": resolved_current,
            "size": resolved_size,
            "total": len(documents),
        }

    async def history_page(
        self,
        user_id: int,
        *,
        session_id: str | None,
        current: int = 1,
        size: int = 10,
    ) -> dict[str, Any]:
        if session_id:
            documents = await self.list_messages(session_id, user_id)
        else:
            sessions = await self.list_sessions(user_id)
            session_ids = {str(item["sessionId"]) for item in sessions}
            all_messages = await _find_many(self.messages, {"delFlag": 0})
            documents = [
                item
                for item in all_messages
                if str(item.get("sessionId")) in session_ids
            ]
            documents.sort(
                key=lambda item: item.get("createTime") or "", reverse=True
            )
        resolved_current = max(current, 1)
        resolved_size = min(max(size, 1), 100)
        start = (resolved_current - 1) * resolved_size
        return {
            "records": documents[start : start + resolved_size],
            "current": resolved_current,
            "size": resolved_size,
            "total": len(documents),
        }

    async def bound_agent_id(self, session_id: str, user_id: int) -> int | None:
        session = await self._require_owned(session_id, user_id)
        value = session.get("agentId")
        return int(value) if value is not None else None

    async def end_session(self, session_id: str, user_id: int) -> None:
        await self._require_owned(session_id, user_id)
        update_one = getattr(self.sessions, "update_one", None)
        if update_one is not None:
            await update_one(
                {"sessionId": session_id, "userId": user_id, "delFlag": 0},
                {"$set": {"status": 2, "endTime": datetime.now(timezone.utc)}},
            )

    async def _require_owned(
        self, session_id: str, user_id: int
    ) -> dict[str, Any]:
        find_one = getattr(self.sessions, "find_one", None)
        if find_one is not None:
            session = await find_one({"sessionId": session_id, "delFlag": 0})
        else:
            matches = await _find_many(self.sessions, {"sessionId": session_id})
            session = matches[0] if matches else None
        if not isinstance(session, dict) or session.get("userId") != user_id:
            raise PermissionError("agent session does not belong to user")
        return session


async def _find_many(collection: Any, query: dict[str, Any]) -> list[dict[str, Any]]:
    result = collection.find(query)
    if inspect.isawaitable(result):
        result = await result
    if isinstance(result, list):
        return list(result)
    to_list = getattr(result, "to_list", None)
    if to_list is not None:
        return list(await to_list(length=None))
    return [item async for item in result]


def _title(first_message: str | None) -> str:
    normalized = " ".join((first_message or "").split()).strip()
    if not normalized:
        return "New Conversation"
    return normalized if len(normalized) <= 20 else f"{normalized[:20]}..."
