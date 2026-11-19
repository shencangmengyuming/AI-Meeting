import json
from collections.abc import AsyncIterator, Sequence
from typing import Any

import httpx

from app.agent.infrastructure.configuration import AgentConfigurationRepository

XUNFEI_WORKFLOW_URL = "https://xingchen-api.xf-yun.com/workflow/v1/chat/completions"


class XunfeiAgentProvider:
    def __init__(
        self,
        configurations: AgentConfigurationRepository,
        http: httpx.AsyncClient,
    ) -> None:
        self.configurations = configurations
        self.http = http

    async def stream(
        self,
        prompt: str,
        *,
        scene: str = "general",
        agent_id: int | None = None,
        aliases: Sequence[str] = (),
        history: list[dict[str, str]] | None = None,
    ) -> AsyncIterator[str]:
        configuration = (
            await self.configurations.resolve_by_id(agent_id)
            if agent_id is not None
            else await self.configurations.resolve(scene, aliases)
        )
        response = await self.http.post(
            XUNFEI_WORKFLOW_URL,
            headers={
                "Content-Type": "application/json",
                "Accept": "text/event-stream",
                "Authorization": (
                    f"Bearer {configuration.api_key}:{configuration.api_secret}"
                ),
            },
            json={
                "flow_id": configuration.flow_id,
                "uid": str(configuration.agent_id),
                "stream": False,
                "chat_id": scene,
                "history": history or [],
                "parameters": {"AGENT_USER_INPUT": prompt},
            },
        )
        if response.status_code != httpx.codes.OK:
            raise ValueError(f"provider request failed: {response.status_code}")
        try:
            payload = response.json()
        except (json.JSONDecodeError, ValueError) as exc:
            raise ValueError("provider response is not JSON") from exc
        content = _extract_content(payload)
        if content is None:
            raise ValueError("provider response has no content")
        yield content

    async def complete(self, prompt: str, *, stream: bool = False) -> list[str]:
        del stream
        return [chunk async for chunk in self.stream(prompt)]


def _extract_content(payload: Any) -> str | None:
    if isinstance(payload, dict):
        content = payload.get("content")
        if isinstance(content, str):
            return content
        choices = payload.get("choices")
        if isinstance(choices, list) and choices:
            first = choices[0]
            if isinstance(first, dict):
                for container_name in ("delta", "message"):
                    container = first.get(container_name)
                    if isinstance(container, dict) and isinstance(
                        container.get("content"), str
                    ):
                        return container["content"]
    return None
