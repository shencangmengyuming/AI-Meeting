import hashlib
import json
from collections.abc import Awaitable
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any, cast

from pymongo.asynchronous.database import AsyncDatabase
from redis.asyncio import Redis

from app.ai_runtime.application.singleflight import DistributedSingleFlight
from app.core.errors import BusinessError
from app.interview.application.ai_guard import AiCallGuard
from app.interview.application.followup_rules import FollowUpRuleChain
from app.interview.application.questions import (
    FLOW_KEY_PREFIX,
    InterviewQuestionService,
)
from app.interview.application.runtime_rehydrate import RuntimeRehydrator
from app.interview.application.turn_compensation import TurnCompensationQueue
from app.interview.domain.flow import (
    InterviewFlowState,
    InterviewFlowStateMachine,
)
from app.interview.domain.follow_up import (
    FollowUpRequest,
    FollowUpRuleContext,
    InterviewFollowUpAgent,
)
from app.interview.domain.scoring import (
    InterviewScoringAgent,
    ScoringRequest,
    ScoringResult,
)

REPLAY_PREFIX = "interview:answer:replay:"
LOCK_PREFIX = "interview:answer:lock:"


class InterviewAnswerService:
    def __init__(
        self,
        database: AsyncDatabase,
        redis: Redis,
        scoring_agent: InterviewScoringAgent,
        follow_up_agent: InterviewFollowUpAgent | None = None,
        ai_guard: AiCallGuard | None = None,
        singleflight: DistributedSingleFlight | None = None,
    ) -> None:
        self.database = database
        self.redis = redis
        self.questions = InterviewQuestionService(database, redis)
        self.scoring_agent = scoring_agent
        self.follow_up_agent = follow_up_agent or _NoFollowUpAgent()
        self.ai_guard = ai_guard or AiCallGuard(timeout_seconds=30, max_retries=0)
        self.singleflight = singleflight or DistributedSingleFlight(redis)
        self.turn_compensation = TurnCompensationQueue(redis)
        self.flow_machine = InterviewFlowStateMachine()
        self.follow_up_rules = FollowUpRuleChain.default()

    async def submit(
        self,
        session_id: str,
        user_id: int,
        question_number: str,
        answer_content: str,
        request_id: str | None,
    ) -> dict[str, Any]:
        if not question_number or not answer_content:
            raise BusinessError("A000001", "题号和答案不能为空")
        await self._ensure_session_can_proceed(session_id, user_id)
        request_id = request_id.strip() if request_id else self._request_id(
            session_id, question_number, answer_content
        )
        replay_key = f"{REPLAY_PREFIX}{session_id}:{request_id}"
        replay = await cast(Awaitable[Any], self.redis.get(replay_key))
        if replay:
            return json.loads(replay)
        archived = await self._archived_response(session_id, user_id, request_id)
        if archived is not None:
            await cast(
                Awaitable[Any],
                self.redis.set(replay_key, json.dumps(archived), ex=86400),
            )
            return archived

        lock_key = f"{LOCK_PREFIX}{session_id}:{question_number}"
        acquired = await cast(
            Awaitable[Any],
            self.redis.set(lock_key, request_id, nx=True, ex=30),
        )
        if not acquired:
            raise BusinessError("A000409", "当前题目正在处理中")
        try:
            questions = await self.questions.get_questions(session_id, user_id)
            flow_key = FLOW_KEY_PREFIX + session_id
            raw_flow = await cast(Awaitable[Any], self.redis.get(flow_key))
            if raw_flow:
                flow = InterviewFlowState.from_mapping(json.loads(raw_flow))
            else:
                recovered = await self.questions._ensure_flow(  # noqa: SLF001
                    session_id, len(questions)
                )
                flow = InterviewFlowState.from_mapping(recovered)
            if flow.finished:
                raise BusinessError("A000409", "面试流程已经完成")
            current = flow.current_question_number
            if current is None:
                raise BusinessError("A000409", "面试流程已经完成")
            if question_number != current:
                raise BusinessError("A000409", "提交题号不是当前活动题目")
            question_content = questions.get(current)
            if question_content is None and _is_follow_up_question(current):
                question_content = await self.questions.get_follow_up_question(
                    session_id,
                    current,
                )
            if question_content is None:
                raise BusinessError("A000404", "当前面试题不存在")

            evaluating_flow = self.flow_machine.move_to_evaluating(flow)
            scoring_request = ScoringRequest(
                session_id=session_id,
                request_id=request_id,
                question_number=current,
                question_content=question_content,
                answer_content=answer_content,
            )
            try:
                async def evaluate() -> Any:
                    return await self.scoring_agent.evaluate(scoring_request)

                flight = await self.singleflight.execute(
                    "interview-scoring",
                    request_id,
                    lambda: self.ai_guard.execute("scoring", evaluate),
                )
                if flight.error:
                    raise RuntimeError(flight.error)
                if flight.result is None:
                    raise RuntimeError("scoring returned no result")
                scoring = (
                    ScoringResult(**flight.result)
                    if isinstance(flight.result, dict)
                    else flight.result
                )
            except BusinessError:
                raise
            except Exception as exc:
                raise BusinessError("B000001", "评分失败") from exc

            current_is_follow_up = _is_follow_up_question(current)
            total_score = flow.total_score + (
                0 if current_is_follow_up else scoring.score
            )
            decision = self.follow_up_rules.decide(
                FollowUpRuleContext(
                    score=scoring.score,
                    missing_points=scoring.missing_points,
                    follow_up_needed_from_ai=scoring.follow_up_needed,
                    follow_up_question_hint=scoring.follow_up_question,
                    follow_up_count=flow.follow_up_count,
                    max_follow_up=flow.max_follow_up,
                    interview_completed=flow.finished,
                )
            )

            next_question_number: str | None = None
            next_question: str | None = None
            next_is_follow_up = False
            if decision.need_follow_up:
                generated = await self.follow_up_agent.generate(
                    FollowUpRequest(
                        session_id=session_id,
                        request_id=request_id,
                        current_question_number=current,
                        current_question=question_content,
                        answer_content=answer_content,
                        fallback_question=scoring.follow_up_question,
                        current_follow_up_count=flow.follow_up_count,
                        max_follow_up=decision.resolved_max_follow_up,
                    )
                )
                if generated is not None:
                    await self.questions.cache_follow_up_question(
                        session_id,
                        generated.question_number,
                        generated.question_content,
                    )
                    next_flow = self.flow_machine.start_follow_up(
                        evaluating_flow,
                        generated.question_number,
                    )
                    next_question_number = generated.question_number
                    next_question = generated.question_content
                    next_is_follow_up = True
                else:
                    next_flow = self.flow_machine.advance_main_question(
                        evaluating_flow
                    )
            else:
                next_flow = self.flow_machine.advance_main_question(evaluating_flow)

            next_flow = replace(next_flow, total_score=total_score)
            if (
                not next_flow.finished
                and not next_is_follow_up
                and next_flow.current_question_number is not None
            ):
                next_question_number = next_flow.current_question_number
                next_question = questions.get(next_question_number)
                if next_question is None:
                    raise BusinessError("A000404", "下一道面试题不存在")

            response: dict[str, Any] = {
                "questionNumber": current,
                "questionContent": question_content,
                "isSuccess": True,
                "finished": next_flow.finished,
                "isFollowUp": next_is_follow_up,
                "followUpCount": next_flow.follow_up_count
                if next_is_follow_up
                else 0,
                "score": scoring.score,
                "totalScore": total_score,
                "feedback": scoring.feedback,
                "missingPoints": list(scoring.missing_points),
                "followUpNeeded": scoring.follow_up_needed,
                "followUpQuestion": scoring.follow_up_question,
                "nextQuestionNumber": next_question_number,
                "nextQuestion": next_question,
            }
            turn = self._build_turn(
                session_id, user_id, request_id, current, question_content,
                answer_content, flow.follow_up_count, response,
            )
            try:
                await self._append_turn(turn)
            except Exception:
                await self.turn_compensation.enqueue(turn)
            await cast(
                Awaitable[Any],
                self.redis.set(
                    flow_key,
                    json.dumps(next_flow.to_mapping()),
                    ex=86400,
                ),
            )
            await self._persist_runtime_snapshot(next_flow, session_id, request_id)
            await cast(
                Awaitable[Any],
                self.redis.set(replay_key, json.dumps(response), ex=86400),
            )
            return response
        finally:
            await cast(Awaitable[Any], self.redis.delete(lock_key))

    async def _append_turn(self, turn: dict[str, Any]) -> None:
        collection: Any = self.database["interview_turn"]
        existing = await collection.find_one(
            {
                "sessionId": turn["sessionId"],
                "requestId": turn["requestId"],
            }
        )
        if existing is not None:
            return
        await collection.insert_one(turn)

    async def _persist_runtime_snapshot(
        self,
        flow: InterviewFlowState,
        session_id: str,
        mutation_id: str,
    ) -> None:
        try:
            collection: Any = self.database["interview_runtime_snapshot"]
        except (KeyError, TypeError):
            return
        if getattr(collection, "replace_one", None) is None:
            return
        existing = await collection.find_one({"sessionId": session_id})
        expected_version = (
            int(existing.get("version", 0))
            if isinstance(existing, dict)
            else 0
        )
        await RuntimeRehydrator(self.redis, collection).refresh_snapshot(
            session_id,
            {
                **flow.to_mapping(),
                "snapshotTime": datetime.now(timezone.utc),
            },
            mutation_id=mutation_id,
            expected_version=expected_version,
        )

    async def _ensure_session_can_proceed(
        self, session_id: str, user_id: int
    ) -> None:
        collection: Any = self.database["interview_session"]
        session = await collection.find_one(
            {"sessionId": session_id, "userId": user_id, "delFlag": 0}
        )
        if session is None:
            session = await collection.find_one(
                {"sessionId": session_id, "userId": user_id}
            )
        if session is None:
            raise BusinessError("A000404", "面试会话不存在")
        status = str(session.get("status") or "").upper()
        if status and status not in {"READY", "IN_PROGRESS"}:
            raise BusinessError("A000409", "当前面试会话不可继续答题")
        if status == "READY":
            now = datetime.now(timezone.utc)
            await collection.update_one(
                {"sessionId": session_id, "userId": user_id},
                {"$set": {"status": "IN_PROGRESS", "startTime": now}},
            )

    async def _archived_response(
        self, session_id: str, user_id: int, request_id: str
    ) -> dict[str, Any] | None:
        collection: Any = self.database["interview_turn"]
        turn = await collection.find_one(
            {
                "sessionId": session_id,
                "userId": user_id,
                "requestId": request_id,
            }
        )
        if not isinstance(turn, dict):
            return None
        response = turn.get("response")
        if isinstance(response, dict):
            return dict(response)
        if "score" not in turn:
            return None
        return {
            "questionNumber": turn.get("questionNumber"),
            "questionContent": turn.get("questionContent"),
            "isSuccess": True,
            "finished": bool(turn.get("finished")),
            "isFollowUp": bool(
                isinstance(turn.get("nextQuestionNumber"), str)
                and "-F" in str(turn["nextQuestionNumber"]).upper()
            ),
            "followUpCount": int(turn.get("followUpCount", 0)),
            "score": int(turn.get("score", 0)),
            "totalScore": int(turn.get("totalScore", 0)),
            "feedback": turn.get("feedback"),
            "missingPoints": list(turn.get("missingPoints", [])),
            "followUpNeeded": bool(turn.get("followUpNeeded")),
            "followUpQuestion": turn.get("followUpQuestion"),
            "nextQuestionNumber": turn.get("nextQuestionNumber"),
            "nextQuestion": turn.get("nextQuestion"),
        }

    @staticmethod
    def _build_turn(
        session_id: str,
        user_id: int,
        request_id: str,
        question_number: str,
        question_content: str,
        answer_content: str,
        current_follow_up_count: int,
        response: dict[str, Any],
    ) -> dict[str, Any]:
        return {
                "sessionId": session_id,
                "userId": user_id,
                "requestId": request_id,
                "questionNumber": question_number,
                "questionContent": question_content,
                "answerContent": answer_content[:1000],
                "score": response["score"],
                "totalScore": response["totalScore"],
                "feedback": response["feedback"],
                "missingPoints": list(response.get("missingPoints", [])),
                "followUpNeeded": bool(response.get("followUpNeeded")),
                "isFollowUp": _is_follow_up_question(question_number),
                "followUpCount": current_follow_up_count,
                "nextQuestionNumber": response["nextQuestionNumber"],
                "nextQuestion": response["nextQuestion"],
                "finished": bool(response["finished"]),
                "response": dict(response),
                "createTime": datetime.now(timezone.utc),
        }

    @staticmethod
    def _request_id(session_id: str, question_number: str, answer: str) -> str:
        seed = f"{session_id}|{question_number}|{answer}".encode()
        return "auto-" + hashlib.sha256(seed).hexdigest()[:32]


class _NoFollowUpAgent:
    async def generate(self, request: FollowUpRequest):
        return None


def _is_follow_up_question(question_number: str) -> bool:
    return "-F" in question_number.upper()
