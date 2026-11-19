from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import AliasChoices, BaseModel, Field

from app.agent.application.chat import AgentChatService
from app.agent.application.files import AgentFileUploadService
from app.agent.application.service import AgentService
from app.agent.application.session import AgentSessionService
from app.agent.application.streaming import AgentStreamEncoder
from app.agent.infrastructure.configuration import (
    AgentConfigurationRepository,
    MySqlAgentConfigurationRepository,
)
from app.agent.infrastructure.file_assets import (
    MySqlAgentFileRepository,
    XunfeiAgentFileUploader,
)
from app.auth_user.api.dependencies import require_current_principal
from app.auth_user.domain.session import AuthPrincipal
from app.core.lifespan import AppResources, get_resources
from app.core.result import Result, success

router = APIRouter(prefix="/api/xunzhi/v1/agent", tags=["agent"])
agents_router = APIRouter(prefix="/api/xunzhi/v1/agents", tags=["agent"])


class AgentStreamRequest(BaseModel):
    prompt: str = Field(
        min_length=1,
        max_length=10000,
        validation_alias=AliasChoices("prompt", "inputMessage"),
    )
    scene: str = Field(default="general", min_length=1, max_length=100)


class AgentSessionCreateRequest(BaseModel):
    first_message: str | None = Field(
        default=None,
        max_length=10000,
        validation_alias=AliasChoices("firstMessage", "title"),
    )


class AgentMessageRequest(BaseModel):
    role: str = Field(default="user", pattern="^(user|assistant)$")
    content: str = Field(min_length=1, max_length=20000)


def get_agent_service(request: Request) -> AgentService:
    service = getattr(request.app.state, "agent_service", None)
    if service is None:
        raise RuntimeError("agent provider is not configured")
    return service


def get_agent_session_service(request: Request) -> AgentSessionService:
    service = getattr(request.app.state, "agent_session_service", None)
    if service is not None:
        return service
    resources: AppResources = get_resources(request)
    service = AgentSessionService(resources.mongo_database)
    request.app.state.agent_session_service = service
    return service


def get_agent_configurations(request: Request) -> AgentConfigurationRepository:
    repository = getattr(request.app.state, "agent_configurations", None)
    if repository is not None:
        return repository
    resources: AppResources = get_resources(request)
    return MySqlAgentConfigurationRepository(resources.session_factory)


def get_agent_file_service(request: Request) -> AgentFileUploadService:
    resources: AppResources = get_resources(request)
    return AgentFileUploadService(
        get_agent_configurations(request),
        XunfeiAgentFileUploader(resources.http),
        MySqlAgentFileRepository(resources.session_factory),
        resources.redis,
        sessions=get_agent_session_service(request),
    )


def get_agent_chat_service(request: Request) -> AgentChatService:
    return AgentChatService(
        get_agent_session_service(request),
        get_agent_service(request),
    )


@agents_router.post("/sessions/{session_id}/chat")
async def chat_agent_session(
    session_id: str,
    payload: AgentStreamRequest,
    principal: AuthPrincipal = Depends(require_current_principal),
    service: AgentChatService = Depends(get_agent_chat_service),
) -> StreamingResponse:
    async def body():
        async for chunk in service.stream(
            session_id,
            principal.user_id,
            payload.prompt,
            payload.scene,
        ):
            yield f"data: {chunk}\n\n"
        yield "event: end\ndata: [DONE]\n\n"

    return StreamingResponse(
        body(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@agents_router.post("/files/upload")
async def upload_agent_file(
    principal: AuthPrincipal = Depends(require_current_principal),
    service: AgentFileUploadService = Depends(get_agent_file_service),
    file: UploadFile = File(...),
    sessionId: str | None = Form(default=None),
    bizType: str | None = Form(default=None),
) -> Result[dict[str, object]]:
    content = await file.read()
    return success(
        await service.upload(
            username=principal.username,
            user_id=principal.user_id,
            session_id=sessionId,
            biz_type=bizType,
            filename=file.filename or "unknown",
            content_type=file.content_type,
            content=content,
        )
    )


@router.post("/sessions")
async def create_agent_session(
    payload: AgentSessionCreateRequest,
    principal: AuthPrincipal = Depends(require_current_principal),
    service: AgentSessionService = Depends(get_agent_session_service),
    configurations: AgentConfigurationRepository = Depends(
        get_agent_configurations
    ),
) -> Result[dict[str, str]]:
    configuration = await configurations.resolve(
        "GENERAL_AGENT_CHAT", aliases=("general", "通用智能体")
    )
    session = await service.create_session(
        principal.user_id,
        agent_id=configuration.agent_id,
        first_message=payload.first_message,
    )
    return success({"sessionId": session.session_id, "title": session.title})


@router.get("/conversations")
async def list_agent_sessions(
    current: int = 1,
    size: int = 10,
    status: int | None = None,
    keyword: str | None = None,
    principal: AuthPrincipal = Depends(require_current_principal),
    service: AgentSessionService = Depends(get_agent_session_service),
) -> Result[dict[str, object]]:
    return success(
        await service.page_sessions(
            principal.user_id,
            current=current,
            size=size,
            status=status,
            keyword=keyword,
        )
    )


@router.post("/sessions/{session_id}/messages")
async def append_agent_message(
    session_id: str,
    payload: AgentMessageRequest,
    principal: AuthPrincipal = Depends(require_current_principal),
    service: AgentSessionService = Depends(get_agent_session_service),
) -> Result[None]:
    await service.append_message(
        session_id,
        principal.user_id,
        payload.role,
        payload.content,
    )
    return success()


@router.get("/conversations/{session_id}/messages")
async def list_agent_messages(
    session_id: str,
    principal: AuthPrincipal = Depends(require_current_principal),
    service: AgentSessionService = Depends(get_agent_session_service),
) -> Result[list[dict[str, object]]]:
    return success(await service.list_messages(session_id, principal.user_id))


@router.put("/conversations/{session_id}/end")
async def end_agent_session(
    session_id: str,
    principal: AuthPrincipal = Depends(require_current_principal),
    service: AgentSessionService = Depends(get_agent_session_service),
) -> Result[None]:
    await service.end_session(session_id, principal.user_id)
    return success()


@agents_router.get("/messages/history")
async def page_agent_messages(
    sessionId: str | None = None,
    current: int = 1,
    size: int = 10,
    principal: AuthPrincipal = Depends(require_current_principal),
    service: AgentSessionService = Depends(get_agent_session_service),
) -> Result[dict[str, object]]:
    return success(
        await service.history_page(
            principal.user_id,
            session_id=sessionId,
            current=current,
            size=size,
        )
    )


# Java-compatible plural routes are kept as aliases for existing clients.
agents_router.add_api_route("/sessions", create_agent_session, methods=["POST"])
agents_router.add_api_route("/conversations", list_agent_sessions, methods=["GET"])
agents_router.add_api_route(
    "/sessions/{session_id}/messages", append_agent_message, methods=["POST"]
)
agents_router.add_api_route(
    "/conversations/{session_id}/messages", list_agent_messages, methods=["GET"]
)
agents_router.add_api_route(
    "/conversations/{session_id}/end", end_agent_session, methods=["PUT"]
)


@router.post("/stream")
async def stream_agent(
    payload: AgentStreamRequest,
    principal: Annotated[AuthPrincipal, Depends(require_current_principal)],
    service: AgentService = Depends(get_agent_service),
) -> StreamingResponse:
    del principal

    async def body():
        encoder = AgentStreamEncoder()
        events = [
            event
            async for event in service.stream(payload.prompt, scene=payload.scene)
        ]
        for chunk in encoder.encode(events):
            yield chunk

    return StreamingResponse(body(), media_type="text/event-stream")
