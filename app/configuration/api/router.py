from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request

from app.auth_user.api.dependencies import require_admin, require_current_principal
from app.auth_user.domain.session import AuthPrincipal
from app.configuration.application.service import ConfigurationService
from app.configuration.infrastructure.repository import MySqlConfigurationRepository
from app.core.lifespan import AppResources, get_resources
from app.core.result import Result, success

router = APIRouter(tags=["configuration"])

AI_COLUMNS = {
    "id": "id",
    "aiName": "ai_name",
    "aiType": "ai_type",
    "apiKey": "api_key",
    "apiSecret": "api_secret",
    "apiUrl": "api_url",
    "modelName": "model_name",
    "maxTokens": "max_tokens",
    "temperature": "temperature",
    "systemPrompt": "system_prompt",
    "isEnabled": "is_enabled",
}
AGENT_COLUMNS = {
    "id": "id",
    "agentName": "agent_name",
    "apiKey": "api_key",
    "apiSecret": "api_secret",
    "apiFlowId": "api_flow_id",
}


def _service(request: Request, table: str) -> ConfigurationService:
    resources: AppResources = get_resources(request)
    columns = AI_COLUMNS if table == "ai_properties" else AGENT_COLUMNS
    return ConfigurationService(
        MySqlConfigurationRepository(
            resources.session_factory, table=table, columns=columns
        )
    )


async def _admin(request: Request, principal: AuthPrincipal) -> None:
    await require_admin(request, principal)


async def _invalidate(request: Request, kind: str) -> None:
    resources: AppResources = get_resources(request)
    await resources.redis.publish(
        "configuration:invalidation", kind
    )


@router.get("/api/xunzhi/v1/ai-properties")
async def page_ai_properties(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_current_principal)],
    current: int = 1,
    size: int = 10,
) -> Result[dict[str, Any]]:
    await _admin(request, principal)
    return success(await _service(request, "ai_properties").page(current, size))


async def get_ai_property(
    item_id: int,
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_current_principal)],
) -> Result[dict[str, Any]]:
    await _admin(request, principal)
    return success(await _service(request, "ai_properties").get(item_id))


@router.post("/api/xunzhi/v1/ai-properties")
async def create_ai_property(
    payload: dict[str, Any],
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_current_principal)],
) -> Result[dict[str, int]]:
    await _admin(request, principal)
    item_id = await _service(request, "ai_properties").create(payload)
    await _invalidate(request, "ai")
    return success({"id": item_id})


@router.put("/api/xunzhi/v1/ai-properties")
async def update_ai_property(
    payload: dict[str, Any],
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_current_principal)],
) -> Result[None]:
    await _admin(request, principal)
    await _service(request, "ai_properties").update(payload)
    await _invalidate(request, "ai")
    return success()


@router.delete("/api/xunzhi/v1/ai-properties/{item_id}")
async def delete_ai_property(
    item_id: int,
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_current_principal)],
) -> Result[None]:
    await _admin(request, principal)
    await _service(request, "ai_properties").delete(item_id)
    await _invalidate(request, "ai")
    return success()


@router.get("/api/xunzhi/v1/ai-properties/enabled")
@router.get("/api/xunzhi/v1/ai-properties/options")
async def enabled_ai_properties(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_current_principal)],
) -> Result[list[dict[str, Any]]]:
    del principal
    return success(await _service(request, "ai_properties").enabled())


@router.put("/api/xunzhi/v1/ai-properties/{item_id}/status")
async def toggle_ai_property(
    item_id: int,
    isEnabled: int,
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_current_principal)],
) -> Result[None]:
    await _admin(request, principal)
    await _service(request, "ai_properties").toggle(item_id, isEnabled)
    await _invalidate(request, "ai")
    return success()


@router.get("/api/xunzhi/v1/agent-properties")
async def page_agent_properties(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_current_principal)],
    current: int = 1,
    size: int = 10,
) -> Result[dict[str, Any]]:
    await _admin(request, principal)
    return success(await _service(request, "agent_properties").page(current, size))


@router.post("/api/xunzhi/v1/agent-properties")
async def create_agent_property(
    payload: dict[str, Any],
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_current_principal)],
) -> Result[dict[str, int]]:
    await _admin(request, principal)
    item_id = await _service(request, "agent_properties").create(payload)
    await _invalidate(request, "agent")
    return success({"id": item_id})


@router.put("/api/xunzhi/v1/agent-properties")
async def update_agent_property(
    payload: dict[str, Any],
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_current_principal)],
) -> Result[None]:
    await _admin(request, principal)
    await _service(request, "agent_properties").update(payload)
    await _invalidate(request, "agent")
    return success()


@router.delete("/api/xunzhi/v1/agent-properties/{item_id}")
async def delete_agent_property(
    item_id: int,
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_current_principal)],
) -> Result[None]:
    await _admin(request, principal)
    await _service(request, "agent_properties").delete(item_id)
    await _invalidate(request, "agent")
    return success()


@router.get("/api/xunzhi/v1/agent-properties/byName")
async def get_agent_property_by_name(
    name: str,
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_current_principal)],
) -> Result[dict[str, Any]]:
    await _admin(request, principal)
    return success(
        await _service(request, "agent_properties").find_by("agentName", name)
    )


# Keep dynamic GET routes last so fixed endpoints such as /enabled aren't shadowed.
router.add_api_route(
    "/api/xunzhi/v1/ai-properties/{item_id}",
    get_ai_property,
    methods=["GET"],
)
