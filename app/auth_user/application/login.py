from app.auth_user.application.passwords import hash_password, verify_password
from app.auth_user.domain.session import (
    AuthCredentialsLookup,
    AuthPrincipal,
    AuthSessionPort,
    AuthToken,
)
from app.core.errors import BusinessError


class UserLoginService:
    def __init__(
        self,
        credentials_lookup: AuthCredentialsLookup,
        sessions: AuthSessionPort,
    ) -> None:
        self.credentials_lookup = credentials_lookup
        self.sessions = sessions

    async def login(
        self, username: str, password: str
    ) -> tuple[AuthToken, AuthPrincipal]:
        credentials = await self.credentials_lookup.find_credentials(username)
        if credentials is None:
            raise BusinessError("A000002", "用户名或密码错误")
        valid, needs_upgrade = verify_password(password, credentials.password)
        if not valid:
            raise BusinessError("A000002", "用户名或密码错误")
        if needs_upgrade:
            await self.credentials_lookup.upgrade_password(
                username, hash_password(password)
            )
        token = await self.sessions.login(username)
        principal = AuthPrincipal(
            user_id=credentials.identity.user_id,
            username=credentials.identity.username,
            token=token.value,
            roles=credentials.identity.roles,
        )
        return token, principal
