import pytest

from app.auth_user.application.login import UserLoginService
from app.auth_user.domain.session import AuthCredentials, AuthIdentity, AuthToken
from app.core.errors import BusinessError


class Credentials:
    def __init__(self, value: AuthCredentials | None) -> None:
        self.value = value

    async def find_credentials(self, username: str) -> AuthCredentials | None:
        return self.value

    async def upgrade_password(self, username: str, password_hash: str) -> None:
        return None


class Sessions:
    async def resolve(self, token: str):
        return None

    async def login(self, username: str) -> AuthToken:
        return AuthToken("python-token", 100)

    async def logout(self, token: str) -> None:
        return None


@pytest.mark.anyio
async def test_login_verifies_password_and_issues_token() -> None:
    service = UserLoginService(
        Credentials(
            AuthCredentials(
                AuthIdentity(42, "alice", frozenset({"user", "admin"})),
                "secret",
            )
        ),
        Sessions(),
    )

    token, principal = await service.login("alice", "secret")

    assert token.value == "python-token"
    assert principal.username == "alice"
    assert "admin" in principal.roles


@pytest.mark.anyio
async def test_login_rejects_unknown_or_wrong_password() -> None:
    service = UserLoginService(Credentials(None), Sessions())

    with pytest.raises(BusinessError) as error:
        await service.login("alice", "wrong")

    assert error.value.code == "A000002"
