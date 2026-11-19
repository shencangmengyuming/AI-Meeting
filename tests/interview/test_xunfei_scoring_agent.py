import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import httpx
import pytest

from app.core.errors import BusinessError
from app.interview.domain.scoring import ScoringRequest
from app.interview.infrastructure import scoring


class MappingResult:
    def __init__(self, row: dict[str, object] | None) -> None:
        self.row = row

    def mappings(self) -> "MappingResult":
        return self

    def first(self) -> dict[str, object] | None:
        return self.row


class Session:
    def __init__(self, row: dict[str, object] | None) -> None:
        self.row = row
        self.parameters: dict[str, object] | None = None

    async def execute(
        self,
        statement: object,
        parameters: dict[str, object],
    ) -> MappingResult:
        self.parameters = parameters
        return MappingResult(self.row)


class SessionFactory:
    def __init__(self, row: dict[str, object] | None) -> None:
        self.session = Session(row)

    @asynccontextmanager
    async def __call__(self) -> AsyncIterator[Session]:
        yield self.session


class StaticAgentConfigurationRepository:
    def __init__(self) -> None:
        self.configuration = scoring.AgentConfiguration(
            agent_id=11,
            agent_name="用户答案评分官",
            api_key="test-api-key",
            api_secret="test-api-secret",
            flow_id="test-flow-id",
        )

    async def resolve_scoring_agent(self) -> object:
        return self.configuration


def scoring_request() -> ScoringRequest:
    return ScoringRequest(
        session_id="session-1",
        request_id="request-1",
        question_number="1",
        question_content="What is idempotency?",
        answer_content="The same request has the same effect.",
    )


@pytest.mark.anyio
async def test_repository_resolves_primary_scoring_agent_configuration() -> None:
    factory = SessionFactory(
        {
            "id": 11,
            "agent_name": "用户答案评分官",
            "api_key": "test-api-key",
            "api_secret": "test-api-secret",
            "api_flow_id": "test-flow-id",
        }
    )
    repository = scoring.MySqlAgentConfigurationRepository(factory)  # type: ignore[arg-type]

    configuration = await repository.resolve_scoring_agent()

    assert configuration == scoring.AgentConfiguration(
        agent_id=11,
        agent_name="用户答案评分官",
        api_key="test-api-key",
        api_secret="test-api-secret",
        flow_id="test-flow-id",
    )
    assert factory.session.parameters == {
        "primary_name": "用户答案评分官",
        "fallback_name": "面试答案评分官",
    }


@pytest.mark.anyio
async def test_repository_rejects_incomplete_scoring_agent_configuration() -> None:
    factory = SessionFactory(
        {
            "id": 11,
            "agent_name": "用户答案评分官",
            "api_key": None,
            "api_secret": "test-api-secret",
            "api_flow_id": "test-flow-id",
        }
    )
    repository = scoring.MySqlAgentConfigurationRepository(factory)  # type: ignore[arg-type]

    with pytest.raises(BusinessError, match="配置不完整"):
        await repository.resolve_scoring_agent()


@pytest.mark.anyio
async def test_xunfei_request_matches_java_workflow_contract() -> None:
    captured: dict[str, Any] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["authorization"] = request.headers["Authorization"]
        captured["accept"] = request.headers["Accept"]
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={"score": 86, "feedback": "Solid answer"},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        agent = scoring.XunfeiScoringAgent(
            StaticAgentConfigurationRepository(), client  # type: ignore[arg-type]
        )
        result = await agent.evaluate(scoring_request())

    assert result.score == 86
    assert captured == {
        "url": "https://xingchen-api.xf-yun.com/workflow/v1/chat/completions",
        "authorization": "Bearer test-api-key:test-api-secret",
        "accept": "text/event-stream",
        "body": {
            "flow_id": "test-flow-id",
            "uid": "123",
            "stream": False,
            "chat_id": "session-1_score",
            "history": [],
            "parameters": {
                "AGENT_USER_INPUT": "The same request has the same effect.",
                "question": "What is idempotency?",
                "resume_context": "",
            },
        },
    }


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("provider_body", "expected_score", "expected_missing_points"),
    [
        (
            {
                "score": 80,
                "feedback": "Direct JSON",
                "missing_points": ["failure handling"],
                "follow_up_needed": True,
                "follow_up_question": "How would you retry?",
            },
            80,
            ("failure handling",),
        ),
        (
            {
                "choices": [
                    {
                        "message": {
                            "content": "```json\n"
                            '{"composite_score": 81, "comment": "Nested", '
                            '"missingPoints": ["monitoring"]}\n```'
                        }
                    }
                ]
            },
            81,
            ("monitoring",),
        ),
        (
            {
                "content": json.dumps(
                    {
                        "json": json.dumps(
                            {
                                "total_score": 82,
                                "suggestion": "Wrapped",
                                "lack_points": "alerts, dashboards",
                            }
                        )
                    }
                )
            },
            82,
            ("alerts", "dashboards"),
        ),
    ],
)
async def test_xunfei_response_normalizes_java_supported_shapes(
    provider_body: dict[str, object],
    expected_score: int,
    expected_missing_points: tuple[str, ...],
) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=provider_body)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        agent = scoring.XunfeiScoringAgent(
            StaticAgentConfigurationRepository(), client  # type: ignore[arg-type]
        )
        result = await agent.evaluate(scoring_request())

    assert result.score == expected_score
    assert result.missing_points == expected_missing_points


@pytest.mark.anyio
@pytest.mark.parametrize(("raw_score", "expected"), [(-20, 0), (135, 100), (84.5, 85)])
async def test_xunfei_response_clamps_and_rounds_score_like_java(
    raw_score: int | float,
    expected: int,
) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"score": raw_score})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        agent = scoring.XunfeiScoringAgent(
            StaticAgentConfigurationRepository(), client  # type: ignore[arg-type]
        )
        result = await agent.evaluate(scoring_request())

    assert result.score == expected


@pytest.mark.anyio
@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(503, json={"message": "unavailable"}),
        httpx.Response(200, json={"code": 10001, "message": "workflow failed"}),
        httpx.Response(200, json={"content": "not-json"}),
    ],
)
async def test_xunfei_provider_or_parse_failure_uses_scoring_business_error(
    response: httpx.Response,
) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return response

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        agent = scoring.XunfeiScoringAgent(
            StaticAgentConfigurationRepository(), client  # type: ignore[arg-type]
        )

        with pytest.raises(BusinessError) as error:
            await agent.evaluate(scoring_request())

    assert error.value.code == "B000001"
