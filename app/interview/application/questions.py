import inspect
import json
from collections.abc import Awaitable, Mapping
from typing import Any, cast

from pymongo.asynchronous.database import AsyncDatabase
from redis.asyncio import Redis

from app.core.errors import BusinessError

QUESTION_CACHE_PREFIX = "interview:questions:session:"
FOLLOW_UP_QUESTION_CACHE_PREFIX = "interview:follow_up_questions:session:"
FLOW_KEY_PREFIX = "interview:flow:session:"


class InterviewQuestionService:
    def __init__(self, database: AsyncDatabase, redis: Redis) -> None:
        self.database = database
        self.redis = redis

    async def get_questions(self, session_id: str, user_id: int) -> dict[str, str]:
        session_collection: Any = self.database["interview_session"]
        question_collection: Any = self.database["interview_question"]
        session = await session_collection.find_one(
            {"sessionId": session_id, "userId": user_id, "delFlag": 0},
            {"_id": 1},
        )
        if session is None:
            raise BusinessError("A000404", "面试会话不存在")

        raw = await cast(
            Awaitable[Mapping[Any, Any]],
            self.redis.hgetall(QUESTION_CACHE_PREFIX + session_id),
        )
        questions = _sorted_questions(raw)
        if questions:
            return questions

        question = await question_collection.find_one(
            {"sessionId": session_id, "delFlag": 0},
            {"questionsJson": 1, "questions": 1},
        )
        if question is None:
            return {}
        questions = _parse_questions(question)
        if questions:
            await cast(
                Awaitable[Any],
                self.redis.hset(
                    QUESTION_CACHE_PREFIX + session_id,
                    mapping=questions,
                ),
            )
        return questions

    async def get_first_question(
        self, session_id: str, user_id: int
    ) -> dict[str, str | bool | None]:
        questions = await self.get_questions(session_id, user_id)
        if not questions:
            raise BusinessError("A000404", "面试题目不存在")
        flow = await self._ensure_flow(session_id, len(questions))
        if bool(flow.get("finished")):
            return {
                "questionNumber": None,
                "questionContent": None,
                "isSuccess": True,
                "finished": True,
            }
        raw_number = flow.get("currentQuestionNumber")
        number = str(raw_number) if raw_number is not None else ""
        content = questions.get(number)
        if content is None and "-F" in number.upper():
            content = await self.get_follow_up_question(session_id, number)
        if content is None:
            raise BusinessError("A000404", "当前面试题不存在")
        return {
            "questionNumber": number,
            "questionContent": content,
            "isSuccess": True,
            "finished": bool(flow["finished"]),
        }

    async def get_follow_up_question(
        self,
        session_id: str,
        question_number: str,
    ) -> str | None:
        raw = await cast(
            Awaitable[Mapping[Any, Any]],
            self.redis.hgetall(FOLLOW_UP_QUESTION_CACHE_PREFIX + session_id),
        )
        normalized = {_text(key): _text(value) for key, value in raw.items()}
        return normalized.get(question_number)

    async def cache_follow_up_question(
        self,
        session_id: str,
        question_number: str,
        question_content: str,
    ) -> None:
        await cast(
            Awaitable[Any],
            self.redis.hset(
                FOLLOW_UP_QUESTION_CACHE_PREFIX + session_id,
                mapping={question_number: question_content},
            ),
        )

    async def _ensure_flow(
        self, session_id: str, total_questions: int
    ) -> dict[str, Any]:
        key = FLOW_KEY_PREFIX + session_id
        raw = await cast(Awaitable[Any], self.redis.get(key))
        if raw:
            decoded = json.loads(raw)
            if isinstance(decoded, dict):
                return decoded
        flow = await self._recover_flow_from_turns(session_id, total_questions)
        await cast(
            Awaitable[Any],
            self.redis.set(key, json.dumps(flow), ex=86400),
        )
        return flow

    async def _recover_flow_from_turns(
        self, session_id: str, total_questions: int
    ) -> dict[str, Any]:
        try:
            snapshots: Any = self.database["interview_runtime_snapshot"]
            snapshot = await snapshots.find_one({"sessionId": session_id})
        except (KeyError, TypeError, AttributeError):
            snapshot = None
        if isinstance(snapshot, dict) and snapshot.get("currentQuestionNumber"):
            return {
                key: value
                for key, value in snapshot.items()
                if key not in {"_id", "sessionId", "snapshotTime", "mutationId"}
            } | {"totalQuestions": total_questions}
        if isinstance(snapshot, dict) and snapshot.get("finished"):
            return {
                "status": "COMPLETED",
                "currentQuestionNumber": None,
                "totalQuestions": total_questions,
                "finished": True,
                "totalScore": int(snapshot.get("totalScore", 0) or 0),
            }
        collection: Any = self.database["interview_turn"]
        find = getattr(collection, "find", None)
        if find is None:
            return {
                "status": "ASKING",
                "currentQuestionNumber": "1",
                "totalQuestions": total_questions,
                "finished": False,
            }
        result = find({"sessionId": session_id})
        if inspect.isawaitable(result):
            result = await result
        if isinstance(result, list):
            turns = list(result)
        elif hasattr(result, "to_list"):
            turns = list(await result.to_list(length=None))
        else:
            turns = [item async for item in result]
        turns.sort(key=lambda item: item.get("createTime") or "")
        latest = turns[-1] if turns else None
        if latest is None:
            return {
                "status": "ASKING",
                "currentQuestionNumber": "1",
                "totalQuestions": total_questions,
                "finished": False,
            }
        finished = bool(latest.get("finished"))
        next_number = latest.get("nextQuestionNumber")
        if finished or next_number is None:
            return {
                "status": "COMPLETED",
                "currentQuestionNumber": None,
                "totalQuestions": total_questions,
                "finished": True,
                "totalScore": int(latest.get("totalScore", 0) or 0),
            }
        normalized = str(next_number)
        main_number = normalized.split("-F", 1)[0]
        current_index = max(int(main_number) - 1, 0) if main_number.isdigit() else 0
        return {
            "status": "FOLLOW_UP" if "-F" in normalized.upper() else "ASKING",
            "currentIndex": current_index,
            "currentQuestionNumber": normalized,
            "totalQuestions": total_questions,
            "followUpCount": int(latest.get("followUpCount", 0) or 0),
            "maxFollowUp": 2,
            "version": max(len(turns), 1),
            "totalScore": int(latest.get("totalScore", 0) or 0),
            "finished": False,
        }


def _parse_questions(document: Mapping[str, Any]) -> dict[str, str]:
    raw_json = document.get("questionsJson")
    if isinstance(raw_json, str) and raw_json.strip():
        try:
            parsed = json.loads(raw_json)
            if isinstance(parsed, dict):
                return _sorted_questions(parsed)
        except json.JSONDecodeError:
            pass
    raw_questions = document.get("questions")
    if isinstance(raw_questions, list):
        return {str(index + 1): str(value) for index, value in enumerate(raw_questions)}
    return {}


def _sorted_questions(values: Mapping[Any, Any]) -> dict[str, str]:
    normalized = {_text(key): _text(value) for key, value in values.items()}
    return dict(
        sorted(
            normalized.items(),
            key=lambda item: (0, int(item[0])) if item[0].isdigit() else (1, item[0]),
        )
    )


def _text(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)
