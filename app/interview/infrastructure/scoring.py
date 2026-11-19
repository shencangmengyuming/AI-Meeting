import json
import math
import re
from dataclasses import dataclass
from typing import Any, Protocol

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.errors import BusinessError
from app.interview.domain.follow_up import (
    FollowUpQuestion,
    FollowUpRequest,
    InterviewFollowUpAgent,
)
from app.interview.domain.scoring import (
    InterviewScoringAgent,
    ScoringRequest,
    ScoringResult,
)

XUNFEI_WORKFLOW_URL = (
    "https://xingchen-api.xf-yun.com/workflow/v1/chat/completions"
)
PRIMARY_SCORING_AGENT_NAME = "用户答案评分官"
FALLBACK_SCORING_AGENT_NAME = "面试答案评分官"
FOLLOW_UP_AGENT_NAME = "面试提问官"


@dataclass(frozen=True)
class AgentConfiguration:
    agent_id: int
    agent_name: str
    api_key: str
    api_secret: str
    flow_id: str


class AgentConfigurationRepository(Protocol):
    async def resolve_scoring_agent(self) -> AgentConfiguration: ...


class FollowUpAgentConfigurationRepository(Protocol):
    async def resolve_follow_up_agent(self) -> AgentConfiguration: ...


class MySqlAgentConfigurationRepository:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self.session_factory = session_factory

    async def resolve_scoring_agent(self) -> AgentConfiguration:
        return await self._resolve_agent(
            PRIMARY_SCORING_AGENT_NAME,
            FALLBACK_SCORING_AGENT_NAME,
        )

    async def resolve_follow_up_agent(self) -> AgentConfiguration:
        return await self._resolve_agent(FOLLOW_UP_AGENT_NAME, FOLLOW_UP_AGENT_NAME)

    async def _resolve_agent(
        self,
        primary_name: str,
        fallback_name: str,
    ) -> AgentConfiguration:
        async with self.session_factory() as session:
            row = (
                await session.execute(
                    text(
                        "SELECT id, agent_name, api_secret, api_key, api_flow_id "
                        "FROM agent_properties "
                        "WHERE del_flag = 0 "
                        "AND agent_name IN (:primary_name, :fallback_name) "
                        "ORDER BY CASE agent_name "
                        "WHEN :primary_name THEN 0 "
                        "WHEN :fallback_name THEN 1 ELSE 2 END "
                        "LIMIT 1"
                    ),
                    {
                        "primary_name": primary_name,
                        "fallback_name": fallback_name,
                    },
                )
            ).mappings().first()

        if row is None:
            raise BusinessError("B000001", "评分 Agent 未配置")
        required_fields = (
            "id",
            "agent_name",
            "api_key",
            "api_secret",
            "api_flow_id",
        )
        if any(
            row.get(field) is None or not str(row[field]).strip()
            for field in required_fields
        ):
            raise BusinessError("B000001", "评分 Agent 配置不完整")
        try:
            configuration = AgentConfiguration(
                agent_id=int(row["id"]),
                agent_name=str(row["agent_name"]).strip(),
                api_key=str(row["api_key"]).strip(),
                api_secret=str(row["api_secret"]).strip(),
                flow_id=str(row["api_flow_id"]).strip(),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise BusinessError("B000001", "评分 Agent 配置不完整") from exc
        return configuration


class XunfeiScoringAgent(InterviewScoringAgent):
    def __init__(
        self,
        configurations: AgentConfigurationRepository,
        http: httpx.AsyncClient,
    ) -> None:
        self.configurations = configurations
        self.http = http

    async def evaluate(self, request: ScoringRequest) -> ScoringResult:
        configuration = await self.configurations.resolve_scoring_agent()
        try:
            response = await self.http.post(
                XUNFEI_WORKFLOW_URL,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "text/event-stream",
                    "Authorization": (
                        f"Bearer {configuration.api_key}:"
                        f"{configuration.api_secret}"
                    ),
                },
                json={
                    "flow_id": configuration.flow_id,
                    "uid": "123",
                    "stream": False,
                    "chat_id": f"{request.session_id}_score",
                    "history": [],
                    "parameters": {
                        "AGENT_USER_INPUT": request.answer_content,
                        "question": request.question_content,
                        "resume_context": "",
                    },
                },
            )
            if response.status_code != httpx.codes.OK:
                raise BusinessError("B000001", "评分 Agent 调用失败")
            result = _parse_scoring_result(response.json())
        except BusinessError:
            raise
        except (httpx.HTTPError, json.JSONDecodeError, TypeError, ValueError) as exc:
            raise BusinessError("B000001", "评分 Agent 响应解析失败") from exc
        return result


class XunfeiFollowUpAgent(InterviewFollowUpAgent):
    def __init__(
        self,
        configurations: FollowUpAgentConfigurationRepository,
        http: httpx.AsyncClient,
    ) -> None:
        self.configurations = configurations
        self.http = http

    async def generate(self, request: FollowUpRequest) -> FollowUpQuestion | None:
        current_count = max(request.current_follow_up_count, 0)
        max_follow_up = request.max_follow_up if request.max_follow_up > 0 else 2
        if current_count >= max_follow_up:
            return None

        next_count = current_count + 1
        question_number = _follow_up_question_number(
            request.current_question_number,
            next_count,
        )
        if question_number is None:
            return None

        generated_question: str | None = None
        try:
            configuration = await self.configurations.resolve_follow_up_agent()
            response = await self.http.post(
                XUNFEI_WORKFLOW_URL,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "text/event-stream",
                    "Authorization": (
                        f"Bearer {configuration.api_key}:"
                        f"{configuration.api_secret}"
                    ),
                },
                json={
                    "flow_id": configuration.flow_id,
                    "uid": "123",
                    "stream": False,
                    "chat_id": request.session_id,
                    "history": [],
                    "parameters": {
                        "AGENT_USER_INPUT": request.answer_content,
                        "mode": "FOLLOW_UP",
                        "follow_up_count": current_count,
                        "max_follow_up": max_follow_up,
                        "question": request.current_question,
                        "resume_context": "",
                    },
                },
            )
            if response.status_code == httpx.codes.OK:
                root = response.json()
                if isinstance(root, dict):
                    response_code = _parse_integer(root.get("code"))
                    if response_code in (None, 0):
                        raw_content = _extract_content_value(root)
                        try:
                            payload = _extract_payload(root)
                        except BusinessError:
                            generated_question = _sanitize_follow_up_question(
                                raw_content
                            )
                        else:
                            if not _as_boolean(payload.get("end_interview")):
                                generated_question = _sanitize_follow_up_question(
                                    payload.get("ask_to_user")
                                )
        except Exception:
            generated_question = None

        question_content = generated_question or _sanitize_follow_up_question(
            request.fallback_question
        )
        if question_content is None:
            return None
        return FollowUpQuestion(
            question_number=question_number,
            question_content=question_content,
            follow_up_count=next_count,
        )


class UnconfiguredScoringAgent(InterviewScoringAgent):
    async def evaluate(self, request: ScoringRequest) -> ScoringResult:
        raise BusinessError("B000001", "评分 Agent 未配置")


def _parse_scoring_result(root: Any) -> ScoringResult:
    if not isinstance(root, dict):
        raise BusinessError("B000001", "评分 Agent 响应解析失败")
    response_code = _parse_integer(root.get("code"))
    if response_code is not None and response_code != 0:
        raise BusinessError("B000001", "评分 Agent 调用失败")

    payload = _extract_payload(root)
    score = _score_from_aliases(payload)
    if score is None:
        raise BusinessError("B000001", "评分结果缺少分数")

    missing_points = _string_list_from_aliases(
        payload,
        "missing_points",
        "missingPoints",
        "lack_points",
    )
    follow_up_question = _string_from_aliases(
        payload,
        "follow_up_question",
        "followUpQuestion",
        "ask_to_user",
        "ask",
    )
    follow_up_value = _first_value(
        payload,
        "follow_up_needed",
        "followUpNeeded",
    )
    if follow_up_value is None:
        logic_ok = _as_boolean(_first_value(payload, "logic_ok", "logicOk"))
        follow_up_needed = (
            not logic_ok or bool(missing_points) or bool(follow_up_question)
        )
    else:
        follow_up_needed = _as_boolean(follow_up_value)

    return ScoringResult(
        score=score,
        feedback=_string_from_aliases(
            payload,
            "feedback",
            "comment",
            "suggestion",
        )
        or "",
        missing_points=missing_points,
        follow_up_needed=follow_up_needed,
        follow_up_question=follow_up_question,
    )


def _extract_payload(root: dict[str, Any]) -> dict[str, Any]:
    content = _extract_content_value(root)
    payload = _as_object(content) if content is not None else root
    if payload is None:
        raise BusinessError("B000001", "评分 Agent 响应解析失败")
    return _unwrap_json_field(payload)


def _extract_content_value(root: dict[str, Any]) -> Any:
    content: Any = None
    choices = root.get("choices")
    if isinstance(choices, list) and choices and isinstance(choices[0], dict):
        first_choice = choices[0]
        for container_name in ("delta", "message"):
            container = first_choice.get(container_name)
            if isinstance(container, dict) and "content" in container:
                content = container["content"]
                break
    if content is None and "content" in root:
        content = root["content"]
    return content


def _as_object(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str) or not value.strip():
        return None

    normalized = _strip_code_fence(value)
    parsed = _load_json_object(normalized)
    if parsed is not None:
        return parsed
    start = normalized.find("{")
    end = normalized.rfind("}")
    if start < 0 or end <= start:
        return None
    return _load_json_object(normalized[start : end + 1])


def _strip_code_fence(value: str) -> str:
    normalized = value.strip()
    if normalized.startswith("```"):
        normalized = re.sub(r"^```[a-zA-Z]*\s*", "", normalized, count=1)
        normalized = re.sub(r"\s*```$", "", normalized, count=1)
    return normalized.strip()


def _load_json_object(value: str) -> dict[str, Any] | None:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _unwrap_json_field(payload: dict[str, Any]) -> dict[str, Any]:
    nested = payload.get("json")
    if isinstance(nested, dict):
        return nested
    parsed = _as_object(nested)
    return parsed if parsed is not None else payload


def _score_from_aliases(payload: dict[str, Any]) -> int | None:
    value = _first_value(payload, "score", "total_score", "composite_score")
    if isinstance(value, bool) or value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(numeric):
        return None
    rounded = math.floor(numeric + 0.5)
    return max(0, min(100, rounded))


def _parse_integer(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _first_value(payload: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in payload:
            return payload[key]
    return None


def _string_from_aliases(payload: dict[str, Any], *keys: str) -> str | None:
    value = _first_value(payload, *keys)
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _string_list_from_aliases(
    payload: dict[str, Any],
    *keys: str,
) -> tuple[str, ...]:
    value = _first_value(payload, *keys)
    if value is None:
        return ()
    if isinstance(value, list):
        return tuple(
            normalized
            for item in value
            if item is not None and (normalized := str(item).strip())
        )
    normalized = str(value).strip()
    if not normalized:
        return ()
    try:
        parsed = json.loads(normalized)
    except json.JSONDecodeError:
        parsed = None
    if isinstance(parsed, list):
        return tuple(
            item_text
            for item in parsed
            if item is not None and (item_text := str(item).strip())
        )
    if re.search(r"[,;，；\n]", normalized):
        return tuple(
            part
            for raw_part in re.split(r"[,;，；\n]+", normalized)
            if (part := raw_part.strip())
        )
    return (normalized,)


def _as_boolean(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"true", "1", "yes"}


def _follow_up_question_number(
    current_question_number: str,
    follow_up_count: int,
) -> str | None:
    normalized = current_question_number.strip()
    if not normalized or follow_up_count <= 0:
        return None
    main_number = normalized.split("-F", 1)[0]
    if not main_number:
        return None
    return f"{main_number}-F{follow_up_count}"


def _sanitize_follow_up_question(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    if not normalized or normalized.lower() in {
        "none",
        "null",
        "n/a",
        "-",
        "__finish__",
    }:
        return None
    if not normalized.endswith("?"):
        normalized += "?"
    return normalized[:100]
