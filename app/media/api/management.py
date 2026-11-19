from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from app.auth_user.api.dependencies import require_admin, require_current_principal
from app.auth_user.domain.session import AuthPrincipal
from app.core.result import Result, success
from app.media.application.connection_registry import ConnectionRegistry
from app.media.application.push_service import WebSocketPushService

router = APIRouter(prefix="/api/xunzhi/v1/websocket", tags=["websocket"])


class PushRequest(BaseModel):
    userId: str
    message: dict[str, object]


def get_registry(request: Request) -> ConnectionRegistry:
    registry = getattr(request.app.state, "media_connections", None)
    if registry is None:
        registry = ConnectionRegistry()
        request.app.state.media_connections = registry
    return registry


def get_push_service(request: Request) -> WebSocketPushService:
    return request.app.state.websocket_push_service


@router.get("/online/{user_id}")
async def online(
    user_id: str,
    principal: Annotated[AuthPrincipal, Depends(require_current_principal)],
    registry: ConnectionRegistry = Depends(get_registry),
) -> Result[dict[str, object]]:
    del principal
    return success({"userId": user_id, "online": await registry.is_online(user_id)})


@router.post("/push")
async def push(
    payload: PushRequest,
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_current_principal)],
    service: WebSocketPushService = Depends(get_push_service),
) -> Result[dict[str, object]]:
    await require_admin(request, principal)
    delivered = await service.push(payload.userId, payload.message)
    return success({"delivered": delivered})


@router.get("/user/{user_id}/status")
async def java_status(
    user_id: str,
    principal: Annotated[AuthPrincipal, Depends(require_current_principal)],
    registry: ConnectionRegistry = Depends(get_registry),
) -> dict[str, object]:
    del principal
    return {"userId": user_id, "isOnline": await registry.is_online(user_id)}


async def _admin_push(
    request: Request,
    principal: AuthPrincipal,
    service: WebSocketPushService,
    user_id: str,
    envelope: dict[str, object],
    success_message: str,
    failure_message: str,
) -> dict[str, object]:
    await require_admin(request, principal)
    delivered = await service.push(user_id, envelope)
    return {
        "success": delivered > 0,
        "message": success_message if delivered > 0 else failure_message,
    }


@router.post("/send-message")
async def java_send_message(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_current_principal)],
    userId: str,
    type: str,
    message: str,
    data: str | None = None,
    service: WebSocketPushService = Depends(get_push_service),
) -> dict[str, object]:
    return await _admin_push(
        request,
        principal,
        service,
        userId,
        {"type": type, "message": message, "data": data},
        "Message delivered",
        "Message delivery failed",
    )


@router.post("/notification/{user_id}")
async def java_notification(
    user_id: str,
    message: str,
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_current_principal)],
    service: WebSocketPushService = Depends(get_push_service),
) -> dict[str, object]:
    return await _admin_push(
        request,
        principal,
        service,
        user_id,
        {"type": "notification", "message": message},
        "Notification delivered",
        "Notification delivery failed",
    )


@router.post("/transcription/{user_id}")
async def java_transcription(
    user_id: str,
    result: str,
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_current_principal)],
    isFinal: bool = False,
    service: WebSocketPushService = Depends(get_push_service),
) -> dict[str, object]:
    return await _admin_push(
        request,
        principal,
        service,
        user_id,
        {"type": "transcription", "result": result, "isFinal": isFinal},
        "Transcription delivered",
        "Transcription delivery failed",
    )


@router.post("/error/{user_id}")
async def java_error(
    user_id: str,
    errorMessage: str,
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_current_principal)],
    service: WebSocketPushService = Depends(get_push_service),
) -> dict[str, object]:
    return await _admin_push(
        request,
        principal,
        service,
        user_id,
        {"type": "error", "message": errorMessage},
        "Error message delivered",
        "Error message delivery failed",
    )
