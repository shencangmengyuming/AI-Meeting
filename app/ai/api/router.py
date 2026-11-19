from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.ai.application.chat import AiChatService
from app.ai.application.conversations import AiConversationService
from app.ai.application.sse import encode_ai_event
from app.ai.infrastructure.configuration import MySqlAiConfigurationRepository
from app.ai.infrastructure.openai_compatible import OpenAiCompatibleProvider
from app.auth_user.api.dependencies import require_current_principal
from app.auth_user.domain.session import AuthPrincipal
from app.core.lifespan import AppResources, get_resources
from app.core.result import Result, success

router = APIRouter(prefix="/api/xunzhi/v1/ai", tags=["ai"])


class AiConversationCreateRequest(BaseModel):
    aiId: int
    firstMessage: str = Field(min_length=1, max_length=10000)


class AiMessageRequest(BaseModel):
    message: str = Field(min_length=1, max_length=20000)


def get_ai_conversation_service(request: Request) -> AiConversationService:
    service = getattr(request.app.state, "ai_conversation_service", None)
    if service is not None:
        return service
    resources: AppResources = get_resources(request)
    return AiConversationService(resources.mongo_database)


def get_ai_chat_service(request: Request) -> AiChatService:
    service = getattr(request.app.state, "ai_chat_service", None)
    if service is not None:
        return service
    resources: AppResources = get_resources(request)
    conversations = get_ai_conversation_service(request)
    return AiChatService(
        conversations,
        MySqlAiConfigurationRepository(resources.session_factory),
        OpenAiCompatibleProvider(resources.http),
    )


@router.post("/conversations")
async def create_conversation(
    payload: AiConversationCreateRequest,
    principal: Annotated[AuthPrincipal, Depends(require_current_principal)],
    service: AiConversationService = Depends(get_ai_conversation_service),
) -> Result[dict[str, object]]:
    return success(
        await service.create(principal.username, payload.aiId, payload.firstMessage)
    )


@router.get("/conversations")
async def page_conversations(
    principal: Annotated[AuthPrincipal, Depends(require_current_principal)],
    current: int = 1,
    size: int = 10,
    service: AiConversationService = Depends(get_ai_conversation_service),
) -> Result[dict[str, object]]:
    return success(
        await service.page(principal.username, current=current, size=min(size, 100))
    )


@router.get("/conversations/{session_id}")
async def get_conversation(
    session_id: str,
    principal: Annotated[AuthPrincipal, Depends(require_current_principal)],
    service: AiConversationService = Depends(get_ai_conversation_service),
) -> Result[dict[str, object]]:
    return success(await service.get(session_id, principal.username))


@router.put("/conversations/{session_id}")
async def update_conversation(
    session_id: str,
    principal: Annotated[AuthPrincipal, Depends(require_current_principal)],
    messageCount: int | None = None,
    title: str | None = None,
    service: AiConversationService = Depends(get_ai_conversation_service),
) -> Result[None]:
    await service.update(
        session_id,
        principal.username,
        title=title,
        message_count=messageCount,
    )
    return success()


@router.put("/conversations/{session_id}/end")
async def end_conversation(
    session_id: str,
    principal: Annotated[AuthPrincipal, Depends(require_current_principal)],
    service: AiConversationService = Depends(get_ai_conversation_service),
) -> Result[None]:
    await service.end(session_id, principal.username)
    return success()


@router.delete("/conversations/{session_id}")
async def delete_conversation(
    session_id: str,
    principal: Annotated[AuthPrincipal, Depends(require_current_principal)],
    service: AiConversationService = Depends(get_ai_conversation_service),
) -> Result[None]:
    await service.delete(session_id, principal.username)
    return success()


async def get_history(
    session_id: str,
    principal: Annotated[AuthPrincipal, Depends(require_current_principal)],
    service: AiConversationService = Depends(get_ai_conversation_service),
) -> Result[list[dict[str, object]]]:
    return success(await service.history(session_id, principal.username))


@router.get("/history/page")
async def page_history(
    principal: Annotated[AuthPrincipal, Depends(require_current_principal)],
    sessionId: str | None = None,
    current: int = 1,
    size: int = 10,
    service: AiConversationService = Depends(get_ai_conversation_service),
) -> Result[dict[str, object]]:
    return success(
        await service.history_page(
            principal.username,
            session_id=sessionId,
            current=current,
            size=min(size, 100),
        )
    )


router.add_api_route("/history/{session_id}", get_history, methods=["GET"])


@router.post("/sessions/{session_id}/chat")
async def chat(
    session_id: str,
    payload: AiMessageRequest,
    principal: Annotated[AuthPrincipal, Depends(require_current_principal)],
    service: AiChatService = Depends(get_ai_chat_service),
) -> StreamingResponse:
    async def body():
        async for kind, content in service.stream(
            session_id, principal.username, payload.message
        ):
            yield encode_ai_event(kind, content)

    return StreamingResponse(
        body(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Cache-Control",
            "X-Accel-Buffering": "no",
        },
    )
