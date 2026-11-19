import pytest
from httpx import ASGITransport, AsyncClient

from app.auth_user.api.user_router import get_registration_service
from app.core.errors import BusinessError
from app.main import create_app


class RegistrationStub:
    async def has_username(self, username: str) -> bool:
        return username == "available"

    async def register(self, **kwargs: object) -> None:
        if kwargs["username"] == "taken":
            raise BusinessError("A000003", "用户名已存在")


@pytest.mark.anyio
async def test_has_username_preserves_available_boolean_contract() -> None:
    app = create_app()
    app.dependency_overrides[get_registration_service] = lambda: RegistrationStub()
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get(
                "/api/xunzhi/v1/users/has-username",
                params={"username": "available"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.json()["data"] is True


@pytest.mark.anyio
async def test_register_returns_success_or_business_error() -> None:
    app = create_app()
    app.dependency_overrides[get_registration_service] = lambda: RegistrationStub()
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            success_response = await client.post(
                "/api/xunzhi/v1/users/register",
                json={"username": "available", "password": "secret"},
            )
            error_response = await client.post(
                "/api/xunzhi/v1/users/register",
                json={"username": "taken", "password": "secret"},
            )
    finally:
        app.dependency_overrides.clear()

    assert success_response.json()["code"] == "0"
    assert error_response.json()["code"] == "A000003"
