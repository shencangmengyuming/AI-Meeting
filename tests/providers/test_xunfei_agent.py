import json
from typing import Any

import httpx
import pytest

from app.agent.domain.configuration import AgentConfiguration
from app.agent.infrastructure.providers.xunfei import XunfeiAgentProvider


class Repository:
    async def resolve(
        self, scene: str, aliases: tuple[str, ...] = ()
    ) -> AgentConfiguration:
        return AgentConfiguration(7, scene, "api-key", "api-secret", "flow-id")


@pytest.mark.anyio
async def test_xunfei_provider_sends_workflow_payload_and_yields_content() -> None:
    captured: dict[str, Any] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["auth"] = request.headers["Authorization"]
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"content": "hello"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = XunfeiAgentProvider(Repository(), client)  # type: ignore[arg-type]
        chunks = [chunk async for chunk in provider.stream("hi", scene="general")]

    assert chunks == ["hello"]
    assert captured == {
        "auth": "Bearer api-key:api-secret",
        "body": {
            "flow_id": "flow-id",
            "uid": "7",
            "stream": False,
            "chat_id": "general",
            "history": [],
            "parameters": {"AGENT_USER_INPUT": "hi"},
        },
    }


@pytest.mark.anyio
async def test_xunfei_provider_rejects_malformed_response() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"content": {"bad": True}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = XunfeiAgentProvider(Repository(), client)  # type: ignore[arg-type]
        with pytest.raises(ValueError, match="provider response"):
            _ = [chunk async for chunk in provider.stream("hi", scene="general")]


@pytest.mark.anyio
async def test_xunfei_provider_reads_delta_content() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"choices": [{"delta": {"content": "hello from delta"}}]},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = XunfeiAgentProvider(Repository(), client)  # type: ignore[arg-type]
        chunks = [chunk async for chunk in provider.stream("hi")]

    assert chunks == ["hello from delta"]
