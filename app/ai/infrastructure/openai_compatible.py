import json
from collections.abc import AsyncIterator
from typing import Any

import httpx


class OpenAiCompatibleProvider:
    def __init__(self, http: httpx.AsyncClient) -> None:
        self.http = http

    async def stream(
        self,
        prompt: str,
        configuration: dict[str, Any],
        history: list[dict[str, Any]],
    ) -> AsyncIterator[tuple[str, str]]:
        api_url = str(configuration.get("apiUrl") or "").rstrip("/")
        api_key = str(configuration.get("apiKey") or "")
        model = str(configuration.get("modelName") or "")
        if not api_url or not api_key or not model:
            raise ValueError("AI configuration is incomplete")
        messages: list[dict[str, str]] = []
        system_prompt = configuration.get("systemPrompt")
        if system_prompt:
            messages.append({"role": "system", "content": str(system_prompt)})
        for item in history:
            role = "user" if int(item.get("messageType", 1)) == 1 else "assistant"
            messages.append(
                {"role": role, "content": str(item.get("messageContent") or "")}
            )
        messages.append({"role": "user", "content": prompt})
        body: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": True,
        }
        if configuration.get("maxTokens") is not None:
            body["max_tokens"] = int(configuration["maxTokens"])
        if configuration.get("temperature") is not None:
            body["temperature"] = float(configuration["temperature"])

        async with self.http.stream(
            "POST",
            f"{api_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "Accept": "text/event-stream",
            },
            json=body,
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line.startswith("data:"):
                    continue
                raw = line[5:].strip()
                if not raw or raw == "[DONE]":
                    continue
                try:
                    payload = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                delta = _delta(payload)
                for kind in ("reasoning_content", "content"):
                    value = delta.get(kind)
                    if isinstance(value, str) and value:
                        yield kind, value


def _delta(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return {}
    first = choices[0]
    if not isinstance(first, dict):
        return {}
    delta = first.get("delta")
    return delta if isinstance(delta, dict) else {}
