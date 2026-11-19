import pytest
from httpx import ASGITransport, AsyncClient

from app.auth_user.api.user_router import get_login_service
from app.auth_user.domain.session import AuthPrincipal, AuthToken
from app.core.errors import BusinessError
from app.main import create_app


class LoginStub:
    async def login(self, username: str, password: str):
        if password != "secret":
            raise BusinessError("A000002", "用户名或密码错误")
        return (
            AuthToken("python-token", 100),
            AuthPrincipal(42, username, "python-token", frozenset({"user", "admin"})),
        )


@pytest.mark.anyio
async def test_login_returns_token_and_admin_flag() -> None:
    app = create_app()
    app.dependency_overrides[get_login_service] = lambda: LoginStub()
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/xunzhi/v1/users/login",
                json={"username": "alice", "password": "secret"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.json() == {
        "code": "0",
        "message": None,
        "data": {
            "token": "python-token",
            "username": "alice",
            "isAdmin": True,
        },
        "requestId": None,
    }


@pytest.mark.anyio
async def test_login_returns_business_error_for_wrong_password() -> None:
    app = create_app()
    app.dependency_overrides[get_login_service] = lambda: LoginStub()
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/xunzhi/v1/users/login",
                json={"username": "alice", "password": "wrong"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["code"] == "A000002"
