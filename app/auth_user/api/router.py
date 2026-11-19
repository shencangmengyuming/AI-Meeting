from fastapi import APIRouter, Depends

from app.auth_user.api.dependencies import require_current_principal
from app.auth_user.domain.session import AuthPrincipal

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/me")
async def current_user(
    principal: AuthPrincipal = Depends(require_current_principal),
) -> dict[str, object]:
    return {
        "userId": principal.user_id,
        "username": principal.username,
        "roles": sorted(principal.roles),
    }
