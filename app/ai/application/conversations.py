import inspect
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


class AiConversationService:
    def __init__(self, database: Any) -> None:
        self.conversations = database["ai_conversation"]
        self.messages = database["ai_message"]

    async def create(
        self, username: str, ai_id: int, first_message: str
    ) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        document: dict[str, Any] = {
            "sessionId": str(uuid4()),
            "username": username,
            "aiId": ai_id,
            "title": _title(first_message),
            "status": 1,
            "messageCount": 0,
            "lastMessageTime": now,
            "createTime": now,
            "updateTime": now,
            "delFlag": 0,
        }
        await self.conversations.insert_one(document)
        return _public_conversation(document)

    async def get(self, session_id: str, username: str) -> dict[str, Any]:
        document = await self.conversations.find_one(
            {"sessionId": session_id, "delFlag": 0}
        )
        self._assert_owner(document, username)
        return _public_conversation(document)

    async def page(
        self, username: str, *, current: int = 1, size: int = 10
    ) -> dict[str, Any]:
        documents = await _find_many(
            self.conversations,
            {"username": username, "delFlag": 0},
        )
        documents.sort(key=lambda item: item.get("createTime") or "", reverse=True)
        start = (max(current, 1) - 1) * max(size, 1)
        selected = documents[start : start + max(size, 1)]
        return {
            "records": [_public_conversation(item) for item in selected],
            "current": max(current, 1),
            "size": max(size, 1),
            "total": len(documents),
        }

    async def update(
        self,
        session_id: str,
        username: str,
        *,
        title: str | None = None,
        message_count: int | None = None,
    ) -> None:
        await self.get(session_id, username)
        values: dict[str, Any] = {"updateTime": datetime.now(timezone.utc)}
        if title is not None:
            values["title"] = title
        if message_count is not None:
            values["messageCount"] = max(message_count, 0)
        await self.conversations.update_one(
            {"sessionId": session_id, "username": username, "delFlag": 0},
            {"$set": values},
        )

    async def end(self, session_id: str, username: str) -> None:
        await self.get(session_id, username)
        await self.conversations.update_one(
            {"sessionId": session_id, "username": username, "delFlag": 0},
            {"$set": {"status": 2, "updateTime": datetime.now(timezone.utc)}},
        )

    async def delete(self, session_id: str, username: str) -> None:
        await self.get(session_id, username)
        await self.conversations.update_one(
            {"sessionId": session_id, "username": username, "delFlag": 0},
            {"$set": {"delFlag": 1, "updateTime": datetime.now(timezone.utc)}},
        )

    async def append_message(
        self,
        session_id: str,
        username: str,
        role: str,
        content: str,
        *,
        reasoning_content: str | None = None,
        error_message: str | None = None,
    ) -> dict[str, Any]:
        await self.get(session_id, username)
        sequence = await self._next_sequence(session_id, username)
        now = datetime.now(timezone.utc)
        document = {
            "sessionId": session_id,
            "messageType": 1 if role == "user" else 2,
            "messageContent": content,
            "reasoningContent": reasoning_content,
            "messageSeq": sequence,
            "errorMessage": error_message,
            "createTime": now,
            "updateTime": now,
            "delFlag": 0,
        }
        await self.messages.insert_one(document)
        return document

    async def history(self, session_id: str, username: str) -> list[dict[str, Any]]:
        await self.get(session_id, username)
        documents = await _find_many(
            self.messages, {"sessionId": session_id, "delFlag": 0}
        )
        documents.sort(key=lambda item: int(item.get("messageSeq", 0)))
        return documents

    async def history_page(
        self,
        username: str,
        *,
        session_id: str | None,
        current: int,
        size: int,
    ) -> dict[str, Any]:
        if session_id:
            documents = await self.history(session_id, username)
        else:
            sessions = await _find_many(
                self.conversations, {"username": username, "delFlag": 0}
            )
            session_ids = {str(item["sessionId"]) for item in sessions}
            all_messages = await _find_many(self.messages, {"delFlag": 0})
            documents = [
                item
                for item in all_messages
                if str(item.get("sessionId")) in session_ids
            ]
            documents.sort(key=lambda item: item.get("createTime") or "", reverse=True)
        start = (max(current, 1) - 1) * max(size, 1)
        return {
            "records": documents[start : start + max(size, 1)],
            "current": max(current, 1),
            "size": max(size, 1),
            "total": len(documents),
        }

    async def _next_sequence(self, session_id: str, username: str) -> int:
        find_one_and_update = getattr(self.conversations, "find_one_and_update", None)
        if find_one_and_update is not None:
            document = await find_one_and_update(
                {"sessionId": session_id, "username": username, "delFlag": 0},
                {
                    "$inc": {"messageCount": 1},
                    "$set": {
                        "lastMessageTime": datetime.now(timezone.utc),
                        "updateTime": datetime.now(timezone.utc),
                    },
                },
                return_document=True,
            )
            if document is None:
                raise PermissionError("AI conversation does not belong to user")
            return int(document.get("messageCount", 0))
        documents = await _find_many(self.messages, {"sessionId": session_id})
        return (
            max(
                (int(item.get("messageSeq", 0)) for item in documents),
                default=0,
            )
            + 1
        )

    @staticmethod
    def _assert_owner(document: Any, username: str) -> None:
        if not isinstance(document, dict) or document.get("username") != username:
            raise PermissionError("AI conversation does not belong to user")


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


def _title(first_message: str) -> str:
    normalized = " ".join(first_message.split()).strip()
    return normalized[:30] or "New Conversation"


def _public_conversation(document: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in document.items() if key != "_id"}
