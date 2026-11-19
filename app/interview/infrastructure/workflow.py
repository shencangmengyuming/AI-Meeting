import json
from typing import Any

import httpx

from app.agent.domain.configuration import AgentConfiguration
from app.interview.infrastructure.scoring import XUNFEI_WORKFLOW_URL


class XunfeiInterviewWorkflow:
    def __init__(self, http: httpx.AsyncClient) -> None:
        self.http = http

    async def invoke(
        self,
        configuration: AgentConfiguration,
        prompt: str,
        file_url: str,
        session_id: str,
    ) -> dict[str, Any]:
        response = await self.http.post(
            XUNFEI_WORKFLOW_URL,
            headers={
                "Authorization": (
                    f"Bearer {configuration.api_key}:{configuration.api_secret}"
                ),
                "Content-Type": "application/json",
            },
            json={
                "flow_id": configuration.flow_id,
                "uid": str(configuration.agent_id),
                "stream": False,
                "chat_id": session_id,
                "history": [],
                "parameters": {
                    "AGENT_USER_INPUT": prompt,
                    "USER_FILE": file_url,
                },
            },
        )
        response.raise_for_status()
        return _structured(response.json())


def _structured(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("workflow response is not an object")

    # A non-streaming XingChen response commonly wraps JSON in
    # choices[0].delta.content (the Java parser accepts the same shape).
    choices = value.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0]
        if isinstance(first, dict):
            for container_name in ("delta", "message"):
                container = first.get(container_name)
                if isinstance(container, dict) and "content" in container:
                    parsed = _content_object(container["content"])
                    if parsed is not None:
                        return parsed

    for key in ("result", "data", "payload"):
        nested = value.get(key)
        if isinstance(nested, dict):
            parsed = _structured(nested)
            if parsed is not nested or any(
                field in parsed for field in ("questions", "resumeScore", "sugest")
            ):
                return parsed
    content = value.get("content")
    if isinstance(content, dict):
        return _structured(content)
    parsed = _content_object(content)
    if parsed is not None:
        return parsed
    if isinstance(value.get("questions"), (list, dict, str)):
        return value
    return value


def _content_object(content: Any) -> dict[str, Any] | None:
    if isinstance(content, dict):
        return content
    if isinstance(content, str):
        cleaned = content.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned[3:]
            if cleaned.startswith("json"):
                cleaned = cleaned[4:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()
        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError:
            return None
        if isinstance(parsed, dict):
            return parsed
    return None
