import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app


@pytest.mark.anyio
async def test_check_login_without_token_returns_logged_out() -> None:
    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/xunzhi/v1/users/check-login")

    assert response.status_code == 200
    assert response.json() == {
        "code": "0",
        "message": None,
        "data": {"isLogin": False},
        "requestId": None,
    }


@pytest.mark.anyio
async def test_is_admin_without_token_returns_false() -> None:
    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/xunzhi/v1/users/is-admin")

    assert response.json()["data"] == {"isAdmin": False}


@pytest.mark.anyio
async def test_logout_without_token_is_idempotent() -> None:
    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app), base_url="http://test"
    ) as client:
        response = await client.post("/api/xunzhi/v1/users/logout")

    assert response.status_code == 200
    assert response.json()["code"] == "0"
