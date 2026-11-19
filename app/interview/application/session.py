import inspect
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

from pymongo.asynchronous.database import AsyncDatabase

from app.core.errors import BusinessError

ACTIVE_STATUSES = ["DRAFT", "RESUME_UPLOADING", "READY", "IN_PROGRESS"]


@dataclass(frozen=True)
class InterviewSessionCreated:
    session_id: str
    status: str


class InterviewSessionService:
    def __init__(self, database: AsyncDatabase) -> None:
        self.database = database
        self.collection = database["interview_session"]

    async def create_session(self, user_id: int) -> InterviewSessionCreated:
        now = datetime.now(timezone.utc)
        await self.collection.update_many(
            {"userId": user_id, "status": {"$in": ACTIVE_STATUSES}, "delFlag": 0},
            {"$set": {"status": "ABANDONED", "endTime": now, "updateTime": now}},
        )
        session_id = str(uuid4())
        await self.collection.insert_one(
            {
                "sessionId": session_id,
                "userId": user_id,
                "status": "DRAFT",
                "conversationTitle": "Interview Session",
                "delFlag": 0,
                "createTime": now,
                "updateTime": now,
            }
        )
        return InterviewSessionCreated(session_id, "DRAFT")

    async def finish_session(self, session_id: str, user_id: int) -> None:
        if not session_id:
            raise BusinessError("A000001", "sessionId不能为空")
        now = datetime.now(timezone.utc)
        result = await self.collection.update_one(
            {
                "sessionId": session_id,
                "userId": user_id,
                "delFlag": 0,
            },
            {"$set": {"status": "FINISHED", "endTime": now, "updateTime": now}},
        )
        if result.matched_count == 0:
            raise BusinessError("A000404", "面试会话不存在")

    async def list_sessions(self, user_id: int) -> list[dict[str, object]]:
        result = self.collection.find({"userId": user_id, "delFlag": 0})
        if inspect.isawaitable(result):
            result = await result
        if isinstance(result, list):
            documents = result
        elif hasattr(result, "to_list"):
            documents = await result.to_list(length=None)
        else:
            documents = [item async for item in result]
        documents.sort(key=lambda item: item.get("createTime") or "", reverse=True)
        return [
            {key: value for key, value in item.items() if key != "_id"}
            for item in documents
        ]

    async def page_sessions(
        self,
        user_id: int,
        *,
        current: int = 1,
        size: int = 10,
        status: str | None = None,
        keyword: str | None = None,
    ) -> dict[str, object]:
        documents = await self.list_sessions(user_id)
        if status:
            documents = [item for item in documents if item.get("status") == status]
        normalized_keyword = (keyword or "").strip().lower()
        if normalized_keyword:
            documents = [
                item
                for item in documents
                if normalized_keyword
                in str(item.get("conversationTitle") or "").lower()
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

    async def restore(self, session_id: str, user_id: int) -> dict[str, object]:
        document = await self.collection.find_one(
            {"sessionId": session_id, "userId": user_id, "delFlag": 0}
        )
        if document is None:
            raise BusinessError("A000404", "面试会话不存在")
        result = {key: value for key, value in document.items() if key != "_id"}
        status = str(result.get("status") or "").upper()
        result["canResume"] = status in {"READY", "IN_PROGRESS"}
        if not result.get("resumeFileUrl") and result.get("resumeUrl"):
            result["resumeFileUrl"] = result["resumeUrl"]
        question = await self.database["interview_question"].find_one(
            {"sessionId": session_id, "delFlag": 0}
        )
        if question:
            if not result.get("resumeFileUrl"):
                result["resumeFileUrl"] = question.get("resumeUrl")
            if not result.get("interviewType"):
                result["interviewType"] = question.get("interviewType")
            result["resumeScore"] = question.get("resumeScore")
            suggestions = question.get("suggestions") or []
            if isinstance(suggestions, dict):
                result["suggestions"] = {
                    str(key): str(value) for key, value in suggestions.items()
                }
            elif isinstance(suggestions, list):
                result["suggestions"] = {
                    str(index + 1): str(value)
                    for index, value in enumerate(suggestions)
                }
        result.setdefault("suggestions", {})
        return result
