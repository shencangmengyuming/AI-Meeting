import json

import httpx
import pytest

from app.interview.infrastructure import scoring


class FollowUpConfigurationRepository:
    async def resolve_follow_up_agent(self):
        return scoring.AgentConfiguration(
            agent_id=12,
            agent_name="面试提问官",
            api_key="test-api-key",
            api_secret="test-api-secret",
            flow_id="test-follow-up-flow",
        )


def follow_up_request():
    from app.interview.domain import follow_up

    return follow_up.FollowUpRequest(
        session_id="session-1",
        request_id="request-1",
        current_question_number="1",
        current_question="What is idempotency?",
        answer_content="The same request has the same effect.",
        fallback_question="Can you give an implementation example",
        current_follow_up_count=0,
        max_follow_up=2,
    )


@pytest.mark.anyio
async def test_xunfei_follow_up_request_and_response_match_java_contract() -> None:
    captured: dict[str, object] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["authorization"] = request.headers["Authorization"]
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "ask_to_user": (
                                        "How do you prevent duplicate writes"
                                    ),
                                    "end_interview": False,
                                }
                            )
                        }
                    }
                ]
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        agent = scoring.XunfeiFollowUpAgent(
            FollowUpConfigurationRepository(), client  # type: ignore[arg-type]
        )
        result = await agent.generate(follow_up_request())

    assert result is not None
    assert result.question_number == "1-F1"
    assert result.question_content == "How do you prevent duplicate writes?"
    assert result.follow_up_count == 1
    assert captured == {
        "authorization": "Bearer test-api-key:test-api-secret",
        "body": {
            "flow_id": "test-follow-up-flow",
            "uid": "123",
            "stream": False,
            "chat_id": "session-1",
            "history": [],
            "parameters": {
                "AGENT_USER_INPUT": "The same request has the same effect.",
                "mode": "FOLLOW_UP",
                "follow_up_count": 0,
                "max_follow_up": 2,
                "question": "What is idempotency?",
                "resume_context": "",
            },
        },
    }


@pytest.mark.anyio
async def test_xunfei_follow_up_failure_uses_scorer_question_fallback() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"message": "unavailable"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        agent = scoring.XunfeiFollowUpAgent(
            FollowUpConfigurationRepository(), client  # type: ignore[arg-type]
        )
        result = await agent.generate(follow_up_request())

    assert result is not None
    assert result.question_number == "1-F1"
    assert result.question_content == "Can you give an implementation example?"


@pytest.mark.anyio
async def test_xunfei_follow_up_accepts_plain_content_question() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"content": "Could you explain transaction isolation"},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        agent = scoring.XunfeiFollowUpAgent(
            FollowUpConfigurationRepository(), client  # type: ignore[arg-type]
        )
        result = await agent.generate(follow_up_request())

    assert result is not None
    assert result.question_content == "Could you explain transaction isolation?"


@pytest.mark.anyio
async def test_xunfei_follow_up_stops_at_configured_limit() -> None:
    request = follow_up_request()
    limited_request = request.__class__(
        **{
            **request.__dict__,
            "current_follow_up_count": 2,
        }
    )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(500, json={})
        )
    ) as client:
        agent = scoring.XunfeiFollowUpAgent(
            FollowUpConfigurationRepository(), client  # type: ignore[arg-type]
        )
        result = await agent.generate(limited_request)

    assert result is None
