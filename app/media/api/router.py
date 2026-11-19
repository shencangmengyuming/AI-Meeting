from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from app.auth_user.api.dependencies import require_current_principal
from app.auth_user.domain.session import AuthPrincipal
from app.core.result import Result, success

router = APIRouter(prefix="/api/xunzhi/v1/xunfei/tts", tags=["tts"])
legacy_router = APIRouter(prefix="/api/xunzhi/v1/tts", tags=["tts"])


class TtsTaskRequest(BaseModel):
    text: str = Field(min_length=1, max_length=100000)


class TtsWaitRequest(BaseModel):
    text: str = Field(min_length=1, max_length=100000)
    timeoutSeconds: float = Field(default=60, gt=0, le=300)


def get_tts_service(request: Request):
    service = getattr(request.app.state, "tts_service", None)
    if service is None:
        raise RuntimeError("tts provider is not configured")
    return service


@router.post("/tasks")
async def create_tts_task(
    payload: TtsTaskRequest,
    principal: Annotated[AuthPrincipal, Depends(require_current_principal)],
    service=Depends(get_tts_service),
) -> Result[dict[str, object]]:
    del principal
    return success(await service.create_task(payload.text))


@router.get("/tasks/{task_id}")
async def query_tts_task(
    task_id: str,
    principal: Annotated[AuthPrincipal, Depends(require_current_principal)],
    service=Depends(get_tts_service),
) -> Result[dict[str, object]]:
    del principal
    return success(await service.query_task(task_id))


@router.post("/synthesize")
async def synthesize_tts(
    payload: TtsWaitRequest,
    principal: Annotated[AuthPrincipal, Depends(require_current_principal)],
    service=Depends(get_tts_service),
) -> Result[dict[str, object]]:
    del principal
    created = await service.create_task(payload.text)
    return success(
        await service.wait_for_task(
            str(created["taskId"]),
            timeout_seconds=payload.timeoutSeconds,
        )
    )


legacy_router.add_api_route("/tasks", create_tts_task, methods=["POST"])
legacy_router.add_api_route("/tasks/{task_id}", query_tts_task, methods=["GET"])
legacy_router.add_api_route("/synthesize", synthesize_tts, methods=["POST"])
