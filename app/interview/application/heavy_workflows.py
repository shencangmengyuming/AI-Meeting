import hashlib
import json
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import Any, Protocol, TypeVar

from app.agent.application.files import AgentFileUploader
from app.agent.infrastructure.configuration import AgentConfigurationRepository
from app.ai_runtime.application.singleflight import DistributedSingleFlight
from app.core.errors import BusinessError
from app.interview.application.ai_guard import AiCallGuard
from app.interview.application.heavy_lock import HeavyTaskLock
from app.interview.application.questions import QUESTION_CACHE_PREFIX
from app.interview.application.runtime_rehydrate import RuntimeRehydrator

T = TypeVar("T")

EXTRACTION_PROMPT = (
    "Extract technical interview questions from the uploaded resume. "
    "Return JSON only with keys questions, sugest, type, and resumeScore. "
    "Do not output smallTalk, greetings, or fallback chat content."
)


class InterviewWorkflow(Protocol):
    async def invoke(
        self,
        configuration: Any,
        prompt: str,
        file_url: str,
        session_id: str,
    ) -> dict[str, Any]: ...


class _OwnedWorkflowService:
    def __init__(
        self,
        database: Any,
        redis: Any,
        *,
        ai_guard: AiCallGuard | None = None,
        singleflight: DistributedSingleFlight | None = None,
        heavy_lock: HeavyTaskLock | None = None,
    ) -> None:
        self.database = database
        self.redis = redis
        self.ai_guard = ai_guard
        self.singleflight = singleflight
        self.heavy_lock = heavy_lock

    async def assert_owner(self, session_id: str, user_id: int) -> None:
        session = await self.database["interview_session"].find_one(
            {"sessionId": session_id, "userId": user_id, "delFlag": 0}
        )
        if session is None:
            session = await self.database["interview_session"].find_one(
                {"sessionId": session_id, "userId": user_id}
            )
        if session is None:
            raise BusinessError("A000404", "面试会话不存在")

    async def assert_can_resume(self, session_id: str, user_id: int) -> None:
        session = await self.database["interview_session"].find_one(
            {"sessionId": session_id, "userId": user_id, "delFlag": 0}
        )
        if session is None:
            session = await self.database["interview_session"].find_one(
                {"sessionId": session_id, "userId": user_id}
            )
        if session is None:
            raise BusinessError("A000404", "面试会话不存在")
        status = str(session.get("status") or "").upper()
        if status and status not in {"READY", "IN_PROGRESS"}:
            raise BusinessError("A000409", "当前面试会话不可继续操作")

    async def execute_heavy(
        self,
        stage: str,
        session_id: str,
        request_key: str,
        operation: Callable[[], Awaitable[T]],
    ) -> T:
        async def guarded() -> T:
            async def invoke() -> T:
                if self.heavy_lock is None:
                    return await operation()
                async with self.heavy_lock.acquire(stage, session_id):
                    return await operation()

            if self.ai_guard is None:
                return await invoke()
            return await self.ai_guard.execute(stage, invoke)

        if self.singleflight is None:
            return await guarded()
        flight = await self.singleflight.execute(stage, request_key, guarded)
        if flight.error:
            raise RuntimeError(flight.error)
        return flight.result  # type: ignore[return-value]


class InterviewExtractionService(_OwnedWorkflowService):
    def __init__(
        self,
        database: Any,
        redis: Any,
        configurations: AgentConfigurationRepository,
        uploader: AgentFileUploader,
        workflow: InterviewWorkflow,
        *,
        ai_guard: AiCallGuard | None = None,
        singleflight: DistributedSingleFlight | None = None,
        heavy_lock: HeavyTaskLock | None = None,
    ) -> None:
        super().__init__(
            database,
            redis,
            ai_guard=ai_guard,
            singleflight=singleflight,
            heavy_lock=heavy_lock,
        )
        self.configurations = configurations
        self.uploader = uploader
        self.workflow = workflow

    async def extract(
        self,
        session_id: str,
        user_id: int,
        filename: str,
        content_type: str | None,
        content: bytes,
    ) -> dict[str, Any]:
        await self.assert_owner(session_id, user_id)
        if not content:
            raise ValueError("resume file cannot be empty")
        request_key = _request_key(session_id, content)
        await _update_session_status(
            self.database,
            session_id,
            user_id,
            "RESUME_UPLOADING",
        )

        async def operation() -> dict[str, Any]:
            configuration = await self.configurations.resolve(
                "INTERVIEW_QUESTION_EXTRACTION",
                aliases=("面试出题官", "简历面试官", "面试问题生成官"),
            )
            file_url = await self.uploader.upload(
                filename, content_type, content, configuration
            )
            payload = await self.workflow.invoke(
                configuration,
                EXTRACTION_PROMPT,
                file_url,
                session_id,
            )
            questions = _strings(payload.get("questions"))
            if not questions:
                raise ValueError("interview workflow returned no questions")
            score = _score(payload.get("resumeScore"))
            suggestions = _strings(
                payload.get("suggestions") or payload.get("sugest")
            )
            document = {
                "sessionId": session_id,
                "questions": questions,
                "questionsJson": json.dumps(
                    {
                        str(index + 1): value
                        for index, value in enumerate(questions)
                    },
                    ensure_ascii=False,
                ),
                "suggestions": suggestions,
                "resumeScore": score,
                "interviewType": payload.get("type"),
                "resumeUrl": file_url,
                "delFlag": 0,
            }
            now = datetime.now(timezone.utc)
            document["updateTime"] = now
            await self.database["interview_question"].update_one(
                {"sessionId": session_id},
                {
                    "$set": document,
                    "$setOnInsert": {"createTime": now},
                },
                upsert=True,
            )
            await self.redis.hset(
                QUESTION_CACHE_PREFIX + session_id,
                mapping={
                    str(index + 1): value
                    for index, value in enumerate(questions)
                },
            )
            if score is not None:
                await self.redis.set(
                    f"interview:resume:score:{session_id}", str(score), ex=86400
                )
            await _update_session_status(
                self.database,
                session_id,
                user_id,
                "READY",
                resume_url=file_url,
                interview_type=payload.get("type"),
            )
            return {
                "questions": questions,
                "suggestions": suggestions,
                "resumeScore": score,
                "type": payload.get("type"),
                "isSuccess": 1,
            }

        try:
            return await self.execute_heavy(
                "resume-extraction", session_id, request_key, operation
            )
        except Exception:
            try:
                await _update_session_status(
                    self.database,
                    session_id,
                    user_id,
                    "DRAFT",
                )
            except Exception:
                pass
            raise


class InterviewDemeanorService(_OwnedWorkflowService):
    def __init__(
        self,
        database: Any,
        redis: Any,
        configurations: AgentConfigurationRepository,
        uploader: AgentFileUploader,
        workflow: InterviewWorkflow,
        *,
        ai_guard: AiCallGuard | None = None,
        singleflight: DistributedSingleFlight | None = None,
        heavy_lock: HeavyTaskLock | None = None,
    ) -> None:
        super().__init__(
            database,
            redis,
            ai_guard=ai_guard,
            singleflight=singleflight,
            heavy_lock=heavy_lock,
        )
        self.configurations = configurations
        self.uploader = uploader
        self.workflow = workflow

    async def evaluate(
        self,
        session_id: str,
        user_id: int,
        filename: str,
        content_type: str | None,
        content: bytes,
    ) -> dict[str, int]:
        await self.assert_owner(session_id, user_id)
        await self.assert_can_resume(session_id, user_id)
        if not content:
            raise ValueError("user photo cannot be empty")
        request_key = _request_key(session_id, content)

        async def operation() -> dict[str, int]:
            configuration = await self.configurations.resolve(
                "INTERVIEW_DEMEANOR",
                aliases=("神态分析官", "神态评估官", "面试神态分析官"),
            )
            file_url = await self.uploader.upload(
                filename, content_type, content, configuration
            )
            payload = await self.workflow.invoke(
                configuration,
                "Evaluate this photo and return integer scores (0-100) for "
                "panicLevel, seriousnessLevel, emoticonHandling and compositeScore.",
                file_url,
                session_id,
            )
            raw = {
                "panicLevel": _required_score(payload, "panicLevel"),
                "seriousnessLevel": _required_score(payload, "seriousnessLevel"),
                "emoticonHandling": _required_score(payload, "emoticonHandling"),
                "compositeScore": _required_score(payload, "compositeScore"),
            }
            ten_scale = all(value <= 10 for value in raw.values())
            normalized = {
                key: min(max(value * 10 if ten_scale else value, 0), 100)
                for key, value in raw.items()
            }
            await self.redis.set(
                f"interview:demeanor:score:{session_id}",
                str(normalized["compositeScore"]),
                ex=86400,
            )
            await self.redis.set(
                f"interview:demeanor:details:{session_id}",
                json.dumps(normalized),
                ex=86400,
            )
            # Keep the Java cache keys as aliases while retaining the Python
            # report key used by the standalone backend.
            for key, value in (
                ("panic", normalized["panicLevel"]),
                ("seriousness", normalized["seriousnessLevel"]),
                ("emoticon", normalized["emoticonHandling"]),
                ("composite", normalized["compositeScore"]),
            ):
                await self.redis.set(
                    f"demeanor:{key}:{session_id}", str(value), ex=86400
                )
            await self._refresh_runtime_snapshot(session_id, normalized)
            return normalized

        return await self.execute_heavy(
            "demeanor-evaluation", session_id, request_key, operation
        )

    async def _refresh_runtime_snapshot(
        self, session_id: str, normalized: dict[str, int]
    ) -> None:
        try:
            collection: Any = self.database["interview_runtime_snapshot"]
            if getattr(collection, "replace_one", None) is None:
                return
            existing = await collection.find_one({"sessionId": session_id})
            if not isinstance(existing, dict):
                return
            expected_version = int(existing.get("version", 0) or 0)
            mutation_id = _request_key(
                session_id, json.dumps(normalized, sort_keys=True).encode()
            )
            await RuntimeRehydrator(self.redis, collection).refresh_snapshot(
                session_id,
                {
                    **existing,
                    "demeanorScore": normalized["compositeScore"],
                    "demeanorDetails": normalized,
                    "snapshotTime": datetime.now(timezone.utc),
                },
                mutation_id=f"demeanor:{mutation_id}",
                expected_version=expected_version,
            )
        except (KeyError, TypeError, ValueError, RuntimeError):
            # Snapshot refresh is a recovery projection; it must not turn a
            # successful demeanor evaluation into a failed user request.
            return


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    if isinstance(value, list):
        return [str(part).strip() for part in value if str(part).strip()]
    return []


def _score(value: Any) -> int | None:
    try:
        return min(max(round(float(value)), 0), 100)
    except (TypeError, ValueError):
        return None


def _required_score(payload: dict[str, Any], key: str) -> int:
    value = _score(payload.get(key))
    if value is None:
        raise ValueError(f"demeanor workflow missing {key}")
    return value


def _request_key(session_id: str, content: bytes) -> str:
    digest = hashlib.sha256(content).hexdigest()
    return f"{session_id}:{digest}"


async def _update_session_status(
    database: Any,
    session_id: str,
    user_id: int,
    status: str,
    *,
    resume_url: str | None = None,
    interview_type: Any = None,
) -> None:
    values: dict[str, Any] = {"status": status}
    if resume_url is not None:
        values["resumeUrl"] = resume_url
    if interview_type is not None:
        values["interviewType"] = interview_type
    await database["interview_session"].update_one(
        {"sessionId": session_id, "userId": user_id},
        {"$set": values},
    )
