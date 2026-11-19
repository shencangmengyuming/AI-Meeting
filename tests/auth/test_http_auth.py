import pytest
from httpx import ASGITransport, AsyncClient

from app.auth_user.api.dependencies import (
    require_admin,
    require_current_principal,
    require_self_or_admin,
)
from app.auth_user.domain.session import AuthPrincipal
from app.main import create_app


@pytest.mark.anyio
async def test_current_user_requires_bearer_token() -> None:
    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/auth/me")

    assert response.status_code == 401
    assert response.json()["code"] == "A000401"


@pytest.mark.anyio
async def test_current_user_rejects_malformed_bearer_token() -> None:
    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(
            "/api/auth/me", headers={"Authorization": "Basic secret"}
        )

    assert response.status_code == 401
    assert response.json()["code"] == "A000401"


@pytest.mark.anyio
async def test_current_user_returns_authenticated_principal() -> None:
    app = create_app()

    async def override() -> AuthPrincipal:
        return AuthPrincipal(
            user_id=42,
            username="fixture-user",
            token="token",
            roles=frozenset({"user", "admin"}),
        )

    app.dependency_overrides[require_current_principal] = override
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get(
                "/api/auth/me", headers={"Authorization": "Bearer token"}
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "userId": 42,
        "username": "fixture-user",
        "roles": ["admin", "user"],
    }


@pytest.mark.anyio
async def test_admin_dependency_rejects_regular_user() -> None:
    from app.core.errors import BusinessError

    request = type("Request", (), {"state": type("State", (), {})()})()

    with pytest.raises(BusinessError) as error:
        await require_admin(
            request,  # type: ignore[arg-type]
            AuthPrincipal(1, "user", "token", frozenset({"user"})),
        )

    assert error.value.code == "A000403"


@pytest.mark.anyio
async def test_self_or_admin_allows_owner_and_admin_only() -> None:
    from app.core.errors import BusinessError

    request = type("Request", (), {"state": type("State", (), {})()})()
    owner = AuthPrincipal(1, "owner", "token", frozenset({"user"}))
    admin = AuthPrincipal(2, "admin", "token", frozenset({"admin"}))

    assert await require_self_or_admin(request, "owner", owner) == owner  # type: ignore[arg-type]
    assert await require_self_or_admin(request, "owner", admin) == admin  # type: ignore[arg-type]
    with pytest.raises(BusinessError) as error:
        await require_self_or_admin(
            request,  # type: ignore[arg-type]
            "other",
            owner,
        )
    assert error.value.code == "A000403"
