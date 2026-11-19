from typing import Annotated

from fastapi import Header, Request

from app.auth_user.domain.session import AuthPrincipal
from app.auth_user.infrastructure.redis_session import RedisSessionAdapter
from app.auth_user.infrastructure.user_identity import MySqlAuthIdentityLookup
from app.core.errors import BusinessError
from app.core.lifespan import AppResources, get_resources


def _bearer_token(authorization: str | None) -> str:
    if not authorization:
        raise BusinessError("A000401", "请先登录", http_status=401)
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise BusinessError("A000401", "登录凭证格式错误", http_status=401)
    return token.strip()


async def resolve_optional_principal(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> AuthPrincipal | None:
    if not authorization:
        return None
    token = _bearer_token(authorization)
    resources: AppResources = get_resources(request)
    identity_lookup = MySqlAuthIdentityLookup(
        resources.session_factory,
        resources.redis,
    )
    return await RedisSessionAdapter(resources.redis, identity_lookup).resolve(token)


async def require_current_principal(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> AuthPrincipal:
    principal = await resolve_optional_principal(request, authorization)
    if principal is None:
        raise BusinessError("A000401", "登录已失效", http_status=401)
    request.state.principal = principal
    return principal


async def require_admin(
    request: Request,
    principal: AuthPrincipal,
) -> AuthPrincipal:
    if "admin" not in principal.roles:
        raise BusinessError("A000403", "无管理员权限", http_status=403)
    request.state.principal = principal
    return principal


async def require_self_or_admin(
    request: Request,
    username: str,
    principal: AuthPrincipal,
) -> AuthPrincipal:
    if principal.username != username and "admin" not in principal.roles:
        raise BusinessError("A000403", "无权访问该用户", http_status=403)
    request.state.principal = principal
    return principal
