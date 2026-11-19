from typing import Annotated, cast

from fastapi import APIRouter, Depends, Header, Request
from pydantic import BaseModel

from app.auth_user.api.dependencies import (
    require_admin,
    require_current_principal,
    require_self_or_admin,
    resolve_optional_principal,
)
from app.auth_user.application.login import UserLoginService
from app.auth_user.application.registration import UserRegistrationService
from app.auth_user.domain.session import AuthIdentityLookup, AuthPrincipal
from app.auth_user.infrastructure.redis_session import RedisSessionAdapter
from app.auth_user.infrastructure.user_identity import MySqlAuthIdentityLookup
from app.auth_user.infrastructure.user_repository import MySqlUserRepository
from app.core.lifespan import AppResources, get_resources
from app.core.result import Result, success

router = APIRouter(prefix="/api/xunzhi/v1/users", tags=["users"])


class LoginRequest(BaseModel):
    username: str
    password: str


class RegisterRequest(BaseModel):
    username: str
    password: str
    realName: str | None = None
    phone: str | None = None
    mail: str | None = None


class UserUpdateRequest(BaseModel):
    realName: str | None = None
    phone: str | None = None
    mail: str | None = None


class AdminGrantRequest(BaseModel):
    username: str


def get_login_service(request: Request) -> UserLoginService:
    resources: AppResources = get_resources(request)
    lookup = MySqlAuthIdentityLookup(resources.session_factory, resources.redis)
    return UserLoginService(
        lookup,
        RedisSessionAdapter(resources.redis, lookup),
    )


def get_registration_service(request: Request) -> UserRegistrationService:
    resources: AppResources = get_resources(request)
    return UserRegistrationService(resources.session_factory, resources.redis)


def get_user_repository(request: Request) -> MySqlUserRepository:
    return MySqlUserRepository(get_resources(request).session_factory)


@router.get("/page")
async def page_users(
    request: Request,
    page: int = 1,
    size: int = 20,
    principal: AuthPrincipal = Depends(require_current_principal),
    repository: MySqlUserRepository = Depends(get_user_repository),
) -> Result[dict[str, object]]:
    await require_admin(request, principal)
    resolved_size = min(max(size, 1), 100)
    records = await repository.page_users(
        (max(page, 1) - 1) * resolved_size,
        resolved_size,
    )
    return success({"records": records, "current": max(page, 1), "size": resolved_size})


@router.get("/actual/{username}")
async def get_actual_user(
    username: str,
    request: Request,
    principal: AuthPrincipal = Depends(require_current_principal),
    repository: MySqlUserRepository = Depends(get_user_repository),
) -> Result[dict[str, object] | None]:
    await require_self_or_admin(request, username, principal)
    user = await repository.get_by_username(username)
    if user and user.get("phone"):
        phone = str(user["phone"])
        user["phone"] = phone[:3] + "****" + phone[-4:] if len(phone) >= 7 else "****"
    return success(user)


async def get_user(
    username: str,
    request: Request,
    principal: AuthPrincipal = Depends(require_current_principal),
    repository: MySqlUserRepository = Depends(get_user_repository),
) -> Result[dict[str, object] | None]:
    await require_self_or_admin(request, username, principal)
    return success(await repository.get_by_username(username))


@router.put("")
async def update_user(
    payload: UserUpdateRequest,
    principal: AuthPrincipal = Depends(require_current_principal),
    repository: MySqlUserRepository = Depends(get_user_repository),
) -> Result[None]:
    await repository.update_self(
        principal.username,
        {
            "real_name": payload.realName,
            "phone": payload.phone,
            "mail": payload.mail,
        },
    )
    return success()


@router.post("/admin")
async def grant_admin(
    payload: AdminGrantRequest,
    request: Request,
    principal: AuthPrincipal = Depends(require_current_principal),
    repository: MySqlUserRepository = Depends(get_user_repository),
) -> Result[None]:
    await require_admin(request, principal)
    await repository.grant_admin(payload.username)
    return success()


@router.get("/has-username")
async def has_username(
    username: str,
    service: UserRegistrationService = Depends(get_registration_service),
) -> Result[bool]:
    return success(await service.has_username(username))


@router.post("/register")
async def register(
    payload: RegisterRequest,
    service: UserRegistrationService = Depends(get_registration_service),
) -> Result[None]:
    await service.register(
        username=payload.username,
        password=payload.password,
        real_name=payload.realName,
        phone=payload.phone,
        mail=payload.mail,
    )
    return success()


@router.post("/login")
async def login(
    payload: LoginRequest,
    service: UserLoginService = Depends(get_login_service),
) -> Result[dict[str, object]]:
    token, principal = await service.login(payload.username, payload.password)
    return success(
        {
            "token": token.value,
            "username": principal.username,
            "isAdmin": "admin" in principal.roles,
        }
    )


@router.get("/check-login")
async def check_login(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> Result[dict[str, object]]:
    principal = await resolve_optional_principal(request, authorization)
    data: dict[str, object] = {"isLogin": principal is not None}
    if principal is not None:
        data.update({"username": principal.username, "token": principal.token})
    return success(data)


@router.get("/is-admin")
async def is_admin(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> Result[dict[str, object]]:
    principal = await resolve_optional_principal(request, authorization)
    data: dict[str, object] = {
        "isAdmin": bool(principal and "admin" in principal.roles)
    }
    if principal is not None:
        data["username"] = principal.username
    return success(data)


@router.post("/logout")
async def logout(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> Result[None]:
    if authorization:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() == "bearer" and token.strip():
            resources: AppResources = get_resources(request)
            await RedisSessionAdapter(
                resources.redis,
                cast(AuthIdentityLookup, object()),
            ).logout(token.strip())
    return success()


# Keep the dynamic username route last so it cannot shadow fixed routes.
router.add_api_route("/{username}", get_user, methods=["GET"])
