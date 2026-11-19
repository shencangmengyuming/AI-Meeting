from collections.abc import AsyncIterator

from app.agent.application.service import AgentService
from app.agent.application.session import AgentSessionService


class AgentChatService:
    def __init__(
        self,
        sessions: AgentSessionService,
        agent: AgentService,
    ) -> None:
        self.sessions = sessions
        self.agent = agent

    async def stream(
        self,
        session_id: str,
        user_id: int,
        prompt: str,
        scene: str,
    ) -> AsyncIterator[str]:
        agent_id = await self.sessions.bound_agent_id(session_id, user_id)
        await self.sessions.append_message(
            session_id, user_id, "user", prompt
        )
        content: list[str] = []
        error: Exception | None = None
        try:
            async for event in self.agent.stream(
                prompt, scene=scene, agent_id=agent_id
            ):
                if event.kind != "content" or event.data is None:
                    continue
                content.append(event.data)
                yield event.data
        except Exception as exc:
            error = exc
            raise
        finally:
            assistant = "".join(content)
            if error is not None and not assistant:
                assistant = f"Provider error: {type(error).__name__}"
            await self.sessions.append_message(
                session_id, user_id, "assistant", assistant
            )
