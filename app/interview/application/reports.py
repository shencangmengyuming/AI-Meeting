import inspect
from typing import Any


class InterviewReportService:
    def __init__(self, database: Any, redis: Any | None = None) -> None:
        self.database = database
        self.redis = redis
        self.turns = database["interview_turn"]

    async def _owned_turns(self, session_id: str, user_id: int) -> list[dict[str, Any]]:
        await self._assert_owner_if_supported(session_id, user_id)
        return await _find(
            self.turns, {"sessionId": session_id, "userId": user_id}
        )

    async def score(self, session_id: str, user_id: int) -> int:
        turns = await self._owned_turns(session_id, user_id)
        scores = [
            int(turn.get("score", 0))
            for turn in turns
            if not turn.get("isFollowUp")
        ]
        return round(sum(scores) / len(scores)) if scores else 0

    async def suggestions(self, session_id: str, user_id: int) -> list[str]:
        turns = await self._owned_turns(session_id, user_id)
        values: list[str] = []
        for turn in turns:
            for point in turn.get("missingPoints", []):
                text = str(point).strip()
                if text and text not in values:
                    values.append(text)
        return values

    async def radar(self, session_id: str, user_id: int) -> dict[str, int]:
        interview_score = await self.score(session_id, user_id)
        resume_score = await self._optional_resume_score(session_id, user_id)
        demeanor_score = await self._optional_demeanor_score(session_id)
        professional = _weighted_average(
            ((resume_score, 0.30), (interview_score, 0.70))
        )
        potential = _weighted_average(
            (
                (resume_score, 0.25),
                (interview_score, 0.55),
                (demeanor_score, 0.20),
            )
        )
        return {
            "resumeScore": resume_score or 0,
            "interviewPerformance": interview_score,
            "demeanorEvaluation": demeanor_score or 0,
            "professionalSkills": professional,
            "potentialIndex": potential,
        }

    async def playback(
        self, session_id: str, user_id: int
    ) -> list[dict[str, Any]]:
        turns = await self._owned_turns(session_id, user_id)
        turns.sort(key=lambda item: item.get("createTime") or "")
        return [
            {key: value for key, value in turn.items() if key != "_id"}
            for turn in turns
        ]

    async def resume_score(self, session_id: str, user_id: int) -> int:
        await self._assert_owner_if_supported(session_id, user_id)
        if self.redis is not None:
            raw = await self.redis.get(f"interview:resume:score:{session_id}")
            if raw is not None:
                if isinstance(raw, bytes):
                    raw = raw.decode("utf-8")
                return int(raw)
        question = await self.database["interview_question"].find_one(
            {"sessionId": session_id, "delFlag": 0}
        )
        return int(question.get("resumeScore", 0)) if question else 0

    async def _assert_owner_if_supported(
        self, session_id: str, user_id: int
    ) -> None:
        sessions = self.database["interview_session"]
        find_one = getattr(sessions, "find_one", None)
        if find_one is None:
            return
        session = await find_one(
            {"sessionId": session_id, "userId": user_id, "delFlag": 0}
        )
        if session is None:
            raise PermissionError("interview session does not belong to user")
        if "userId" not in session:
            return

    async def _optional_resume_score(
        self, session_id: str, user_id: int
    ) -> int | None:
        await self._assert_owner_if_supported(session_id, user_id)
        if self.redis is not None:
            raw = await self.redis.get(f"interview:resume:score:{session_id}")
            if raw is not None:
                if isinstance(raw, bytes):
                    raw = raw.decode("utf-8")
                try:
                    return max(0, min(100, int(float(raw))))
                except (TypeError, ValueError):
                    return None
        question = await self.database["interview_question"].find_one(
            {"sessionId": session_id, "delFlag": 0}
        )
        if not question or question.get("resumeScore") is None:
            return None
        try:
            return max(0, min(100, int(float(question["resumeScore"]))))
        except (TypeError, ValueError):
            return None

    async def _optional_demeanor_score(self, session_id: str) -> int | None:
        if self.redis is None:
            return None
        raw = await self.redis.get(f"interview:demeanor:score:{session_id}")
        if raw is None:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        try:
            return max(0, min(100, int(float(raw))))
        except (TypeError, ValueError):
            return None


def _weighted_average(values: tuple[tuple[int | None, float], ...]) -> int:
    available = [
        (max(0, min(100, score)), weight)
        for score, weight in values
        if score is not None
    ]
    if not available:
        return 0
    total_weight = sum(weight for _, weight in available)
    weighted = sum(score * weight for score, weight in available)
    return max(0, min(100, round(weighted / total_weight)))


async def _find(collection: Any, query: dict[str, Any]) -> list[dict[str, Any]]:
    result = collection.find(query)
    if inspect.isawaitable(result):
        result = await result
    if isinstance(result, list):
        return list(result)
    to_list = getattr(result, "to_list", None)
    if to_list is not None:
        return list(await to_list(length=None))
    return [item async for item in result]
