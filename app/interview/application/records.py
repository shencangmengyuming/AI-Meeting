import asyncio
import inspect
import json
from datetime import datetime, timezone
from typing import Any

from app.core.errors import BusinessError


class InterviewRecordService:
    def __init__(self, database: Any, redis: Any | None = None) -> None:
        self.database = database
        self.redis = redis
        self.turns = database["interview_turn"]
        self.records = database["interview_record"]

    async def finalize(self, session_id: str, user_id: int) -> dict[str, Any]:
        if self.redis is None:
            return await self._finalize_unlocked(session_id, user_id)
        lock_key = f"interview:finalize:lock:{session_id}"
        token = f"{user_id}:{datetime.now(timezone.utc).timestamp()}"
        for attempt in range(3):
            acquired = await self.redis.set(lock_key, token, nx=True, ex=30)
            if acquired:
                try:
                    return await self._finalize_unlocked(session_id, user_id)
                finally:
                    await self.redis.delete(lock_key)
            if attempt < 2:
                await asyncio.sleep(0.05 * (attempt + 1))
        raise BusinessError("A000409", "finalize is processing, please retry")

    async def _finalize_unlocked(
        self, session_id: str, user_id: int
    ) -> dict[str, Any]:
        turns = await _find(
            self.turns, {"sessionId": session_id, "userId": user_id}
        )
        turns.sort(key=lambda item: item.get("createTime") or "")
        main_turns = [turn for turn in turns if not turn.get("isFollowUp")]
        scores = [int(turn.get("score", 0)) for turn in main_turns]
        score = round(sum(scores) / len(scores)) if scores else 0
        now = datetime.now(timezone.utc)
        improvement_tips: list[str] = []
        for turn in turns:
            for point in turn.get("missingPoints", []):
                value = str(point).strip()
                if value and value not in improvement_tips:
                    improvement_tips.append(value)
        playback = [
            {
                "seq": index,
                **{
                    key: value
                    for key, value in turn.items()
                    if key not in {"_id", "userId", "sessionId"}
                },
            }
            for index, turn in enumerate(turns, start=1)
        ]
        feedback = [
            str(turn.get("feedback"))
            for turn in turns
            if turn.get("feedback")
        ]
        session = await self.database["interview_session"].find_one(
            {"sessionId": session_id, "userId": user_id, "delFlag": 0}
        )
        question = await self.database["interview_question"].find_one(
            {"sessionId": session_id, "delFlag": 0}
        )
        resume_score = _safe_score(question.get("resumeScore")) if question else None
        question_count = _question_count(question)
        suggestions = _suggestion_map(question.get("suggestions")) if question else {}
        interview_status = str((session or {}).get("status") or "FINALIZED")
        interview_direction = (session or {}).get("interviewType")
        snapshot = {
            "sessionId": session_id,
            "status": interview_status,
            "resumeScore": resume_score,
            "interviewScore": score,
            "questionCount": question_count,
            "interviewDirection": interview_direction,
        }
        record = {
            "sessionId": session_id,
            "userId": user_id,
            "interviewScore": score,
            "totalScore": score,
            "resumeScore": resume_score,
            "interviewStatus": interview_status,
            "questionCount": question_count,
            "interviewDirection": interview_direction,
            "interviewSuggestions": ",".join(suggestions.values()) or None,
            "interviewSuggestionsMap": suggestions,
            "sessionSnapshotJson": json.dumps(snapshot, ensure_ascii=False),
            "answerCount": len(main_turns),
            "feedback": feedback,
            "playbackItems": playback,
            "reviewFeedback": {
                "overallComment": feedback[-1] if feedback else "",
                "highlights": feedback,
                "improvementTips": improvement_tips,
                "nextActions": improvement_tips,
            },
            "status": "FINALIZED",
            "createTime": now,
            "updateTime": now,
            "delFlag": 0,
        }
        query = {"sessionId": session_id, "userId": user_id, "delFlag": 0}
        existing = await self.records.find_one(query)
        if existing is None:
            # The unique session/user key is enforced by Mongo; upsert makes
            # concurrent finalization safe.
            await self.records.update_one(
                query,
                {"$setOnInsert": record},
                upsert=True,
            )
        else:
            changed = {
                key: value
                for key, value in record.items()
                if key not in {"createTime", "delFlag", "updateTime"}
                and existing.get(key) != value
            }
            if changed:
                changed["updateTime"] = now
                await self.records.update_one(query, {"$set": changed})
        persisted = await self.records.find_one(
            {"sessionId": session_id, "userId": user_id, "delFlag": 0}
        )
        return _public(persisted or record)

    async def save(
        self,
        session_id: str,
        user_id: int,
        values: dict[str, Any],
    ) -> None:
        now = datetime.now(timezone.utc)
        existing = await self.records.find_one(
            {"sessionId": session_id, "userId": user_id, "delFlag": 0}
        )
        document = {
            "sessionId": session_id,
            "userId": user_id,
            "interviewScore": max(int(values.get("interviewScore") or 0), 0),
            "interviewSuggestions": values.get("interviewSuggestions"),
            "interviewDirection": values.get("interviewDirection"),
            "status": "FINALIZED",
            "updateTime": now,
            "delFlag": 0,
        }
        if existing is None:
            document["createTime"] = now
            await self.records.insert_one(document)
            return
        await self.records.update_one(
            {"sessionId": session_id, "userId": user_id, "delFlag": 0},
            {"$set": document},
        )

    async def get(self, session_id: str, user_id: int) -> dict[str, Any] | None:
        record = await self.records.find_one(
            {"sessionId": session_id, "userId": user_id, "delFlag": 0}
        )
        return _public(record) if record else None

    async def list(self, user_id: int) -> list[dict[str, Any]]:
        records = await _find(self.records, {"userId": user_id, "delFlag": 0})
        records.sort(key=lambda item: item.get("createTime") or "", reverse=True)
        return [_public(record) for record in records]

    async def page(
        self,
        user_id: int,
        *,
        current: int = 1,
        size: int = 10,
        session_id: str | None = None,
        min_score: int | None = None,
        max_score: int | None = None,
        direction: str | None = None,
    ) -> dict[str, Any]:
        records = await self.list(user_id)
        if session_id:
            records = [item for item in records if item.get("sessionId") == session_id]
        if min_score is not None:
            records = [
                item
                for item in records
                if int(item.get("interviewScore", 0)) >= min_score
            ]
        if max_score is not None:
            records = [
                item
                for item in records
                if int(item.get("interviewScore", 0)) <= max_score
            ]
        normalized_direction = (direction or "").strip().lower()
        if normalized_direction:
            records = [
                item
                for item in records
                if normalized_direction
                in str(item.get("interviewDirection") or "").lower()
            ]
        resolved_current = max(current, 1)
        resolved_size = min(max(size, 1), 100)
        start = (resolved_current - 1) * resolved_size
        return {
            "records": records[start : start + resolved_size],
            "current": resolved_current,
            "size": resolved_size,
            "total": len(records),
        }


async def _find(collection: Any, query: dict[str, Any]) -> list[dict[str, Any]]:
    result = collection.find(query)
    if inspect.isawaitable(result):
        result = await result
    if isinstance(result, list):
        return result
    if hasattr(result, "to_list"):
        return list(await result.to_list(length=None))
    return [item async for item in result]


def _public(record: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in record.items() if key != "_id"}


def _safe_score(value: Any) -> int | None:
    try:
        return max(0, min(100, round(float(value))))
    except (TypeError, ValueError):
        return None


def _question_count(question: dict[str, Any] | None) -> int:
    if not question:
        return 0
    values = question.get("questions")
    if isinstance(values, list):
        return len(values)
    raw = question.get("questionsJson")
    if isinstance(raw, str):
        try:
            decoded = json.loads(raw)
            return len(decoded) if isinstance(decoded, dict) else 0
        except json.JSONDecodeError:
            return 0
    return 0


def _suggestion_map(value: Any) -> dict[str, str]:
    if isinstance(value, dict):
        return {str(key): str(item) for key, item in value.items()}
    if isinstance(value, list):
        return {str(index + 1): str(item) for index, item in enumerate(value)}
    if isinstance(value, str) and value.strip():
        return {"1": value.strip()}
    return {}
