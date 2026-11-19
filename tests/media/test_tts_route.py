import pytest
from httpx import ASGITransport, AsyncClient

from app.auth_user.api.dependencies import require_current_principal
from app.auth_user.domain.session import AuthPrincipal
from app.main import create_app


class TtsStub:
    async def create_task(self, text: str) -> dict[str, object]:
        return {"taskId": "task-1", "textLength": len(text)}


@pytest.mark.anyio
async def test_tts_route_requires_auth_and_returns_task() -> None:
    app = create_app()
    app.dependency_overrides[require_current_principal] = lambda: AuthPrincipal(
        1, "user", "token", frozenset({"user"})
    )
    app.state.tts_service = TtsStub()
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/xunzhi/v1/xunfei/tts/tasks",
                json={"text": "hello"},
                headers={"Authorization": "Bearer token"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["data"]["taskId"] == "task-1"
