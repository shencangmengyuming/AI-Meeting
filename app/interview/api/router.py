from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.agent.infrastructure.configuration import (
    MySqlAgentConfigurationRepository as GeneralAgentConfigurationRepository,
)
from app.agent.infrastructure.file_assets import XunfeiAgentFileUploader
from app.ai_runtime.application.singleflight import DistributedSingleFlight
from app.auth_user.api.dependencies import require_current_principal
from app.auth_user.domain.session import AuthPrincipal
from app.core.errors import BusinessError
from app.core.lifespan import AppResources, get_resources
from app.core.result import Result, success
from app.interview.application.ai_guard import AiCallGuard
from app.interview.application.answers import InterviewAnswerService
from app.interview.application.heavy_lock import HeavyTaskLock
from app.interview.application.heavy_workflows import (
    InterviewDemeanorService,
    InterviewExtractionService,
)
from app.interview.application.questions import InterviewQuestionService
from app.interview.application.records import InterviewRecordService
from app.interview.application.reports import InterviewReportService
from app.interview.application.resume_preview import (
    InterviewResumePreviewService,
    ResumePreviewDownloadError,
    ResumePreviewSourceError,
)
from app.interview.application.session import InterviewSessionService
from app.interview.infrastructure.scoring import (
    MySqlAgentConfigurationRepository,
    XunfeiFollowUpAgent,
    XunfeiScoringAgent,
)
from app.interview.infrastructure.workflow import XunfeiInterviewWorkflow

router = APIRouter(prefix="/api/xunzhi/v1/interview", tags=["interview"])


class InterviewAnswerRequest(BaseModel):
    questionNumber: str = Field(min_length=1, max_length=32)
    answerContent: str = Field(min_length=1, max_length=5000)
    requestId: str | None = Field(default=None, max_length=64)


class InterviewRecordSaveRequest(BaseModel):
    sessionId: str = Field(min_length=1, max_length=64)
    interviewScore: int | None = Field(default=None, ge=0)
    interviewSuggestions: str | None = Field(default=None, max_length=10000)
    interviewDirection: str | None = Field(default=None, max_length=128)


def get_interview_session_service(request: Request) -> InterviewSessionService:
    resources: AppResources = get_resources(request)
    return InterviewSessionService(resources.mongo_database)


def get_interview_question_service(request: Request) -> InterviewQuestionService:
    resources: AppResources = get_resources(request)
    return InterviewQuestionService(resources.mongo_database, resources.redis)


def get_interview_answer_service(request: Request) -> InterviewAnswerService:
    resources: AppResources = get_resources(request)
    agent_configurations = MySqlAgentConfigurationRepository(
        resources.session_factory
    )
    scoring_agent = XunfeiScoringAgent(
        agent_configurations,
        resources.http,
    )
    follow_up_agent = XunfeiFollowUpAgent(
        agent_configurations,
        resources.http,
    )
    return InterviewAnswerService(
        resources.mongo_database,
        resources.redis,
        scoring_agent,
        follow_up_agent,
    )


def get_interview_report_service(request: Request) -> InterviewReportService:
    resources = get_resources(request)
    return InterviewReportService(resources.mongo_database, resources.redis)


def get_resume_preview_service(request: Request) -> InterviewResumePreviewService:
    resources = get_resources(request)
    return InterviewResumePreviewService(resources.mongo_database, resources.http)


def get_interview_record_service(request: Request) -> InterviewRecordService:
    resources = get_resources(request)
    return InterviewRecordService(resources.mongo_database, resources.redis)


def get_extraction_service(request: Request) -> InterviewExtractionService:
    resources: AppResources = get_resources(request)
    return InterviewExtractionService(
        resources.mongo_database,
        resources.redis,
        GeneralAgentConfigurationRepository(resources.session_factory),
        XunfeiAgentFileUploader(resources.http),
        XunfeiInterviewWorkflow(resources.http),
        ai_guard=AiCallGuard(timeout_seconds=60, max_retries=1),
        singleflight=DistributedSingleFlight(resources.redis, ttl_seconds=120),
        heavy_lock=HeavyTaskLock(resources.redis, ttl_seconds=180),
    )


def get_demeanor_service(request: Request) -> InterviewDemeanorService:
    resources: AppResources = get_resources(request)
    return InterviewDemeanorService(
        resources.mongo_database,
        resources.redis,
        GeneralAgentConfigurationRepository(resources.session_factory),
        XunfeiAgentFileUploader(resources.http),
        XunfeiInterviewWorkflow(resources.http),
        ai_guard=AiCallGuard(timeout_seconds=60, max_retries=1),
        singleflight=DistributedSingleFlight(resources.redis, ttl_seconds=120),
        heavy_lock=HeavyTaskLock(resources.redis, ttl_seconds=180),
    )


@router.post("/sessions")
async def create_session(
    principal: Annotated[AuthPrincipal, Depends(require_current_principal)],
    service: InterviewSessionService = Depends(get_interview_session_service),
) -> Result[dict[str, str]]:
    created = await service.create_session(principal.user_id)
    return success({"sessionId": created.session_id, "status": created.status})


@router.put("/sessions/{session_id}/finish")
async def finish_session(
    session_id: str,
    principal: Annotated[AuthPrincipal, Depends(require_current_principal)],
    service: InterviewSessionService = Depends(get_interview_session_service),
    record_service: InterviewRecordService = Depends(get_interview_record_service),
) -> Result[None]:
    await record_service.finalize(session_id, principal.user_id)
    await service.finish_session(session_id, principal.user_id)
    await record_service.finalize(session_id, principal.user_id)
    return success()


@router.put("/conversations/{session_id}/end")
async def end_interview_conversation(
    session_id: str,
    principal: Annotated[AuthPrincipal, Depends(require_current_principal)],
    service: InterviewSessionService = Depends(get_interview_session_service),
    record_service: InterviewRecordService = Depends(get_interview_record_service),
) -> Result[None]:
    await record_service.finalize(session_id, principal.user_id)
    await service.finish_session(session_id, principal.user_id)
    await record_service.finalize(session_id, principal.user_id)
    return success()


@router.get("/conversations")
async def list_interview_conversations(
    principal: Annotated[AuthPrincipal, Depends(require_current_principal)],
    service: InterviewSessionService = Depends(get_interview_session_service),
    current: int = 1,
    size: int = 10,
    status: str | None = None,
    keyword: str | None = None,
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


@router.get("/sessions/{session_id}/restore")
async def restore_interview_session(
    session_id: str,
    principal: Annotated[AuthPrincipal, Depends(require_current_principal)],
    service: InterviewSessionService = Depends(get_interview_session_service),
) -> Result[dict[str, object]]:
    return success(await service.restore(session_id, principal.user_id))


@router.post("/sessions/{session_id}/interview-questions")
async def extract_interview_questions(
    session_id: str,
    principal: Annotated[AuthPrincipal, Depends(require_current_principal)],
    resumePdf: UploadFile = File(...),
    service: InterviewExtractionService = Depends(get_extraction_service),
) -> Result[dict[str, object]]:
    try:
        result = await service.extract(
            session_id,
            principal.user_id,
            resumePdf.filename or "resume.pdf",
            resumePdf.content_type,
            await resumePdf.read(),
        )
    except (ValueError, RuntimeError) as exc:
        message = str(exc).strip() or "简历解析失败，请稍后重试"
        raise BusinessError("B000001", message) from exc
    return success(result)


@router.post("/sessions/{session_id}/demeanor-evaluation")
async def evaluate_demeanor(
    session_id: str,
    principal: Annotated[AuthPrincipal, Depends(require_current_principal)],
    userPhoto: UploadFile = File(...),
    service: InterviewDemeanorService = Depends(get_demeanor_service),
) -> Result[str]:
    await service.evaluate(
        session_id,
        principal.user_id,
        userPhoto.filename or "photo.jpg",
        userPhoto.content_type,
        await userPhoto.read(),
    )
    return success("Demeanor evaluation completed")


@router.get("/sessions/{session_id}/interview/questions")
async def get_session_questions(
    session_id: str,
    principal: Annotated[AuthPrincipal, Depends(require_current_principal)],
    service: InterviewQuestionService = Depends(get_interview_question_service),
) -> Result[dict[str, str]]:
    return success(await service.get_questions(session_id, principal.user_id))


@router.get("/sessions/{session_id}/current-question")
@router.get("/sessions/{session_id}/next-question")
async def get_current_question(
    session_id: str,
    principal: Annotated[AuthPrincipal, Depends(require_current_principal)],
    service: InterviewQuestionService = Depends(get_interview_question_service),
) -> Result[dict[str, str | bool | None]]:
    return success(await service.get_first_question(session_id, principal.user_id))


@router.post("/sessions/{session_id}/interview/answer-json")
async def answer_question(
    session_id: str,
    payload: InterviewAnswerRequest,
    principal: Annotated[AuthPrincipal, Depends(require_current_principal)],
    service: InterviewAnswerService = Depends(get_interview_answer_service),
) -> Result[dict[str, object]]:
    return success(
        await service.submit(
            session_id,
            principal.user_id,
            payload.questionNumber,
            payload.answerContent,
            payload.requestId,
        )
    )


@router.post("/sessions/{session_id}/interview/answer")
async def answer_question_form(
    session_id: str,
    principal: Annotated[AuthPrincipal, Depends(require_current_principal)],
    questionNumber: str = Form(min_length=1, max_length=32),
    answerContent: str = Form(min_length=1, max_length=5000),
    requestId: str | None = Form(default=None, max_length=64),
    service: InterviewAnswerService = Depends(get_interview_answer_service),
) -> Result[dict[str, object]]:
    return success(
        await service.submit(
            session_id,
            principal.user_id,
            questionNumber,
            answerContent,
            requestId,
        )
    )


@router.get("/sessions/{session_id}/interview/score")
async def get_interview_score(
    session_id: str,
    principal: Annotated[AuthPrincipal, Depends(require_current_principal)],
    service: InterviewReportService = Depends(get_interview_report_service),
) -> Result[int]:
    return success(await service.score(session_id, principal.user_id))


@router.get("/sessions/{session_id}/interview/suggestions")
async def get_interview_suggestions(
    session_id: str,
    principal: Annotated[AuthPrincipal, Depends(require_current_principal)],
    service: InterviewReportService = Depends(get_interview_report_service),
) -> Result[dict[str, str]]:
    suggestions = await service.suggestions(session_id, principal.user_id)
    return success(
        {str(index + 1): value for index, value in enumerate(suggestions)}
    )


@router.get("/sessions/{session_id}/resume/score")
async def get_resume_score(
    session_id: str,
    principal: Annotated[AuthPrincipal, Depends(require_current_principal)],
    service: InterviewReportService = Depends(get_interview_report_service),
) -> Result[int]:
    return success(await service.resume_score(session_id, principal.user_id))


@router.get("/conversations/{session_id}/messages")
async def get_interview_messages(
    session_id: str,
    principal: Annotated[AuthPrincipal, Depends(require_current_principal)],
    service: InterviewReportService = Depends(get_interview_report_service),
) -> Result[list[dict[str, object]]]:
    return success(await service.playback(session_id, principal.user_id))


@router.get("/messages/history")
async def page_interview_messages(
    principal: Annotated[AuthPrincipal, Depends(require_current_principal)],
    sessionId: str,
    current: int = 1,
    size: int = 10,
    service: InterviewReportService = Depends(get_interview_report_service),
) -> Result[dict[str, object]]:
    messages = await service.playback(sessionId, principal.user_id)
    resolved_current = max(current, 1)
    resolved_size = min(max(size, 1), 100)
    start = (resolved_current - 1) * resolved_size
    return success(
        {
            "records": messages[start : start + resolved_size],
            "current": resolved_current,
            "size": resolved_size,
            "total": len(messages),
        }
    )


@router.get("/sessions/{session_id}/resume/preview")
async def preview_resume(
    session_id: str,
    principal: Annotated[AuthPrincipal, Depends(require_current_principal)],
    service: InterviewResumePreviewService = Depends(get_resume_preview_service),
) -> Response:
    try:
        resource = await service.load(session_id, principal.user_id)
    except ResumePreviewSourceError as exc:
        return Response(
            str(exc), status_code=400, media_type="text/plain; charset=utf-8"
        )
    except ResumePreviewDownloadError as exc:
        return Response(
            str(exc), status_code=502, media_type="text/plain; charset=utf-8"
        )
    except Exception:
        return Response(
            "Failed to preview resume",
            status_code=500,
            media_type="text/plain; charset=utf-8",
        )
    encoded_name = quote(resource.filename, safe="")
    return Response(
        resource.content,
        media_type=resource.content_type,
        headers={
            "Content-Length": str(len(resource.content)),
            "Cache-Control": "no-store, must-revalidate",
            "Pragma": "no-cache",
            "Content-Disposition": f"inline; filename*=UTF-8''{encoded_name}",
        },
    )


@router.get("/sessions/{session_id}/radar-chart")
async def get_interview_radar(
    session_id: str,
    principal: Annotated[AuthPrincipal, Depends(require_current_principal)],
    service: InterviewReportService = Depends(get_interview_report_service),
) -> Result[dict[str, int]]:
    return success(await service.radar(session_id, principal.user_id))


@router.post("/interview/record/save-from-redis/{session_id}")
async def finalize_interview_record(
    session_id: str,
    principal: Annotated[AuthPrincipal, Depends(require_current_principal)],
    service: InterviewRecordService = Depends(get_interview_record_service),
) -> Result[dict[str, object]]:
    return success(await service.finalize(session_id, principal.user_id))


@router.post("/interview/record")
async def save_interview_record(
    payload: InterviewRecordSaveRequest,
    principal: Annotated[AuthPrincipal, Depends(require_current_principal)],
    service: InterviewRecordService = Depends(get_interview_record_service),
) -> Result[None]:
    await service.save(
        payload.sessionId,
        principal.user_id,
        payload.model_dump(exclude={"sessionId"}),
    )
    return success()


@router.get("/interview/record/{session_id}")
async def get_interview_record(
    session_id: str,
    principal: Annotated[AuthPrincipal, Depends(require_current_principal)],
    service: InterviewRecordService = Depends(get_interview_record_service),
) -> Result[dict[str, object] | None]:
    return success(await service.get(session_id, principal.user_id))


@router.get("/interview/records")
async def list_interview_records(
    principal: Annotated[AuthPrincipal, Depends(require_current_principal)],
    service: InterviewRecordService = Depends(get_interview_record_service),
    pageNum: int = 1,
    pageSize: int = 10,
    sessionId: str | None = None,
    minScore: int | None = None,
    maxScore: int | None = None,
    interviewDirection: str | None = None,
) -> Result[dict[str, object]]:
    return success(
        await service.page(
            principal.user_id,
            current=pageNum,
            size=pageSize,
            session_id=sessionId,
            min_score=minScore,
            max_score=maxScore,
            direction=interviewDirection,
        )
    )
