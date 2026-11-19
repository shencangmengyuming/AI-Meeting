import pytest
from httpx import ASGITransport, AsyncClient

from app.agent.api.router import get_agent_chat_service
from app.agent.application.chat import AgentChatService
from app.agent.domain.streaming import StreamEvent
from app.auth_user.api.dependencies import require_current_principal
from app.auth_user.domain.session import AuthPrincipal
from app.main import create_app


class Chat:
    async def stream(self, session_id, user_id, prompt, scene):
        assert (session_id, user_id, prompt) == ("s1", 7, "hello")
        yield '{"content":"answer"}'


class BoundSessions:
    def __init__(self) -> None:
        self.messages: list[tuple[str, int, str, str]] = []

    async def bound_agent_id(self, session_id: str, user_id: int) -> int:
        assert (session_id, user_id) == ("s1", 7)
        return 42

    async def append_message(
        self, session_id: str, user_id: int, role: str, content: str
    ) -> None:
        self.messages.append((session_id, user_id, role, content))


class BoundAgent:
    def __init__(self) -> None:
        self.agent_ids: list[int | None] = []

    async def stream(self, prompt: str, *, scene: str, agent_id: int | None = None):
        assert (prompt, scene) == ("hello", "client-scene")
        self.agent_ids.append(agent_id)
        yield StreamEvent("content", "answer")


@pytest.mark.anyio
async def test_agent_chat_prefers_session_bound_agent() -> None:
    sessions = BoundSessions()
    agent = BoundAgent()
    service = AgentChatService(sessions, agent)  # type: ignore[arg-type]

    chunks = [
        chunk
        async for chunk in service.stream("s1", 7, "hello", "client-scene")
    ]

    assert chunks == ["answer"]
    assert agent.agent_ids == [42]
    assert [message[2:] for message in sessions.messages] == [
        ("user", "hello"),
        ("assistant", "answer"),
    ]


@pytest.mark.anyio
async def test_agent_chat_uses_agent_sse_end_contract() -> None:
    app = create_app()
    app.dependency_overrides[require_current_principal] = lambda: AuthPrincipal(
        7, "owner", "token", frozenset({"user"})
    )
    app.dependency_overrides[get_agent_chat_service] = lambda: Chat()
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/xunzhi/v1/agents/sessions/s1/chat",
                json={"inputMessage": "hello"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.text == (
        'data: {"content":"answer"}\n\n'
        "event: end\n"
        "data: [DONE]\n\n"
    )
