import inspect
import json
from typing import Any

from app.interview.domain.runtime import RuntimeView, SnapshotResult


class RuntimeRehydrator:
    def __init__(
        self,
        redis: Any,
        snapshot_collection: Any,
        turn_collection: Any | None = None,
    ) -> None:
        self.redis = redis
        self.snapshot_collection = snapshot_collection
        self.turn_collection = turn_collection

    async def ensure_runtime(self, session_id: str) -> RuntimeView:
        key = f"interview:runtime:{session_id}"
        raw = await self.redis.get(key)
        if raw:
            state = _decode(raw)
            if state:
                return RuntimeView(session_id, state, "REDIS", "HIGH")

        snapshot = await self.snapshot_collection.find_one({"sessionId": session_id})
        if snapshot:
            state = dict(snapshot)
            await self.redis.set(key, json.dumps(state, default=str), ex=86400)
            return RuntimeView(session_id, state, "MONGO_SNAPSHOT", "MEDIUM")

        turns = await self._turns(session_id)
        if turns:
            turns.sort(key=lambda item: item.get("createTime") or "")
            latest = turns[-1]
            finished = bool(latest.get("finished"))
            question_number = latest.get("nextQuestionNumber")
            state = {
                "sessionId": session_id,
                "status": (
                    "COMPLETED"
                    if finished
                    else "FOLLOW_UP"
                    if isinstance(question_number, str)
                    and "-F" in question_number.upper()
                    else "ASKING"
                ),
                "currentQuestionNumber": None if finished else question_number,
                "followUpCount": int(latest.get("followUpCount", 0)),
                "totalScore": int(latest.get("totalScore", 0)),
                "finished": finished,
                "version": len(turns),
                "lastRequestId": latest.get("requestId"),
            }
            await self.redis.set(key, json.dumps(state, default=str), ex=86400)
            return RuntimeView(session_id, state, "TURN_ARCHIVE", "MEDIUM")

        state = {"sessionId": session_id, "status": "INIT", "version": 1}
        await self.redis.set(key, json.dumps(state), ex=86400)
        return RuntimeView(session_id, state, "NEW", "LOW")

    async def _turns(self, session_id: str) -> list[dict[str, Any]]:
        if self.turn_collection is None:
            return []
        result = self.turn_collection.find({"sessionId": session_id})
        if inspect.isawaitable(result):
            result = await result
        if isinstance(result, list):
            return list(result)
        to_list = getattr(result, "to_list", None)
        if to_list is not None:
            return list(await to_list(length=None))
        return [item async for item in result]

    async def refresh_snapshot(
        self,
        session_id: str,
        state: dict[str, Any],
        *,
        mutation_id: str,
        expected_version: int,
    ) -> SnapshotResult:
        existing = await self.snapshot_collection.find_one({"sessionId": session_id})
        if existing and existing.get("mutationId") == mutation_id:
            return SnapshotResult(
                version=int(existing.get("version", expected_version)),
                state=existing,
                applied=False,
            )
        current_version = int(existing.get("version", 0)) if existing else 0
        if current_version != expected_version:
            raise RuntimeError("runtime snapshot version conflict")
        document = {
            **state,
            "sessionId": session_id,
            "version": expected_version + 1,
            "mutationId": mutation_id,
        }
        # Only the first snapshot may use an upsert. Once a document exists,
        # a stale version must fail the conditional replacement instead of
        # attempting to insert a second document with the same session id.
        upsert = existing is None and expected_version == 0
        result = await self.snapshot_collection.replace_one(
            {"sessionId": session_id, "version": expected_version},
            document,
            upsert=upsert,
        )
        matched = int(getattr(result, "matched_count", 0) or 0)
        upserted = getattr(result, "upserted_id", None)
        if matched == 0 and upserted is None:
            raise RuntimeError("runtime snapshot version conflict")
        await self.redis.set(
            f"interview:runtime:{session_id}",
            json.dumps(document, default=str),
            ex=86400,
        )
        return SnapshotResult(document["version"], document, True)


def _decode(raw: Any) -> dict[str, Any]:
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    value = json.loads(raw) if isinstance(raw, str) else raw
    return value if isinstance(value, dict) else {}
