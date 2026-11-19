from collections.abc import AsyncIterator
from typing import Any

from app.agent.domain.streaming import AgentProvider, StreamEvent


class AgentService:
    def __init__(self, provider: AgentProvider) -> None:
        self.provider = provider

    async def stream(
        self,
        prompt: str,
        *,
        scene: str = "general",
        agent_id: int | None = None,
    ) -> AsyncIterator[StreamEvent]:
        provider_stream = getattr(self.provider, "stream", None)
        if provider_stream is not None:
            async for chunk in provider_stream(
                prompt, scene=scene, agent_id=agent_id
            ):
                yield StreamEvent("content", str(chunk))
            yield StreamEvent("done", None)
            return
        chunks: Any = await self.provider.complete(prompt, stream=True)
        for chunk in chunks:
            yield StreamEvent("content", str(chunk))
        yield StreamEvent("done", None)
