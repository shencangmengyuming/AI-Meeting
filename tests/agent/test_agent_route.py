import pytest
from httpx import ASGITransport, AsyncClient

from app.agent.application.service import AgentService
from app.auth_user.api.dependencies import require_current_principal
from app.auth_user.domain.session import AuthPrincipal
from app.main import create_app


class StubProvider:
    async def complete(self, prompt: str, *, stream: bool = False):
        return ["hello"]


@pytest.mark.anyio
async def test_agent_stream_route_emits_sse() -> None:
    app = create_app()
    app.dependency_overrides[require_current_principal] = lambda: AuthPrincipal(
        1, "user", "token", frozenset({"user"})
    )
    app.state.agent_service = AgentService(StubProvider())
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/xunzhi/v1/agent/stream",
                json={"prompt": "hi"},
                headers={"Authorization": "Bearer token"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.text == "event: content\ndata: hello\n\nevent: done\ndata: {}\n\n"
