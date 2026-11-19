import pytest
from httpx import ASGITransport, AsyncClient

from app.auth_user.api.dependencies import require_current_principal
from app.auth_user.domain.session import AuthPrincipal
from app.main import create_app
from app.media.api.management import get_push_service, get_registry


class Registry:
    async def is_online(self, user_id):
        return user_id == "7"


class Push:
    def __init__(self):
        self.values = []

    async def push(self, user_id, envelope):
        self.values.append((user_id, envelope))
        return 1


@pytest.mark.anyio
async def test_java_compatible_websocket_management_routes_return_naked_json() -> None:
    app = create_app()
    push = Push()
    app.dependency_overrides[require_current_principal] = lambda: AuthPrincipal(
        1, "admin", "token", frozenset({"admin"})
    )
    app.dependency_overrides[get_registry] = lambda: Registry()
    app.dependency_overrides[get_push_service] = lambda: push
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            status = await client.get(
                "/api/xunzhi/v1/websocket/user/7/status"
            )
            sent = await client.post(
                "/api/xunzhi/v1/websocket/send-message",
                params={"userId": "7", "type": "notice", "message": "hello"},
            )
            notification = await client.post(
                "/api/xunzhi/v1/websocket/notification/7",
                params={"message": "hello"},
            )
            transcription = await client.post(
                "/api/xunzhi/v1/websocket/transcription/7",
                params={"result": "text", "isFinal": "true"},
            )
            error = await client.post(
                "/api/xunzhi/v1/websocket/error/7",
                params={"errorMessage": "bad"},
            )
    finally:
        app.dependency_overrides.clear()

    assert status.json() == {"userId": "7", "isOnline": True}
    assert sent.json() == {"success": True, "message": "Message delivered"}
    assert notification.json()["message"] == "Notification delivered"
    assert transcription.json()["message"] == "Transcription delivered"
    assert error.json()["message"] == "Error message delivered"
    assert push.values == [
        ("7", {"type": "notice", "message": "hello", "data": None}),
        ("7", {"type": "notification", "message": "hello"}),
        ("7", {"type": "transcription", "result": "text", "isFinal": True}),
        ("7", {"type": "error", "message": "bad"}),
    ]
