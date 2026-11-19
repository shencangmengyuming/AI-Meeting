import json

import httpx
import pytest

from app.ai.infrastructure.openai_compatible import OpenAiCompatibleProvider


@pytest.mark.anyio
async def test_openai_provider_normalizes_content_and_reasoning_chunks() -> None:
    captured = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["authorization"] = request.headers["Authorization"]
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            text=(
                'data: {"choices":[{"delta":{"reasoning_content":"think"}}]}\n\n'
                'data: {"choices":[{"delta":{"content":"answer"}}]}\n\n'
                "data: [DONE]\n\n"
            ),
            headers={"content-type": "text/event-stream"},
        )

    configuration = {
        "apiUrl": "https://provider.test/v1",
        "apiKey": "secret-key",
        "modelName": "model",
        "maxTokens": 200,
        "temperature": 0.3,
        "systemPrompt": "system",
    }
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = OpenAiCompatibleProvider(client)
        chunks = [
            item
            async for item in provider.stream("hello", configuration, [])
        ]

    assert chunks == [("reasoning_content", "think"), ("content", "answer")]
    assert captured["authorization"] == "Bearer secret-key"
    assert captured["body"]["stream"] is True
