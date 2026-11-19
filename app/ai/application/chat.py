from collections.abc import AsyncIterator
from typing import Any, Protocol

from app.ai.application.conversations import AiConversationService


class AiConfigurationRepository(Protocol):
    async def get_enabled(self, ai_id: int) -> Any: ...


class AiChatProvider(Protocol):
    def stream(
        self,
        prompt: str,
        configuration: Any,
        history: list[dict[str, Any]],
    ) -> AsyncIterator[tuple[str, str]]: ...


class AiChatService:
    def __init__(
        self,
        conversations: AiConversationService,
        configurations: AiConfigurationRepository,
        provider: AiChatProvider,
    ) -> None:
        self.conversations = conversations
        self.configurations = configurations
        self.provider = provider

    async def stream(
        self, session_id: str, username: str, prompt: str
    ) -> AsyncIterator[tuple[str, str]]:
        conversation = await self.conversations.get(session_id, username)
        history = await self.conversations.history(session_id, username)
        configuration = await self.configurations.get_enabled(
            int(conversation["aiId"])
        )
        await self.conversations.append_message(
            session_id, username, "user", prompt
        )
        content_parts: list[str] = []
        reasoning_parts: list[str] = []
        error: str | None = None
        try:
            async for kind, content in self.provider.stream(
                prompt, configuration, history
            ):
                if kind == "reasoning_content":
                    reasoning_parts.append(content)
                else:
                    content_parts.append(content)
                yield kind, content
        except Exception as exc:
            error = str(exc)
            raise
        finally:
            await self.conversations.append_message(
                session_id,
                username,
                "assistant",
                "".join(content_parts),
                reasoning_content="".join(reasoning_parts) or None,
                error_message=error,
            )
