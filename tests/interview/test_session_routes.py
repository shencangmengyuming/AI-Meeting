import pytest
from httpx import ASGITransport, AsyncClient

from app.auth_user.api.dependencies import require_current_principal
from app.auth_user.domain.session import AuthPrincipal
from app.interview.api.router import (
    get_extraction_service,
    get_interview_record_service,
    get_interview_session_service,
)
from app.interview.application.session import InterviewSessionCreated
from app.main import create_app


class SessionStub:
    async def create_session(self, user_id: int) -> InterviewSessionCreated:
        assert user_id == 42
        return InterviewSessionCreated("session-1", "DRAFT")

    async def finish_session(self, session_id: str, user_id: int) -> None:
        assert session_id == "session-1"
        assert user_id == 42

    async def page_sessions(self, user_id: int, **filters):
        assert user_id == 42
        assert filters == {
            "current": 2,
            "size": 5,
            "status": "FINISHED",
            "keyword": "python",
        }
        return {"records": [], "current": 2, "size": 5, "total": 0}


class RecordStub:
    def __init__(self) -> None:
        self.finalized = []

    async def finalize(self, session_id: str, user_id: int) -> dict[str, object]:
        self.finalized.append((session_id, user_id))
        return {"sessionId": session_id}


class ExtractionStub:
    async def extract(self, *args, **kwargs):
        raise ValueError("interview workflow returned no questions")


@pytest.mark.anyio
async def test_create_session_uses_authenticated_user() -> None:
    app = create_app()
    app.dependency_overrides[require_current_principal] = lambda: AuthPrincipal(
        42, "alice", "token", frozenset({"user"})
    )
    app.dependency_overrides[get_interview_session_service] = lambda: SessionStub()
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/xunzhi/v1/interview/sessions",
                headers={"Authorization": "Bearer token"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.json()["data"] == {"sessionId": "session-1", "status": "DRAFT"}


@pytest.mark.anyio
async def test_finish_session_uses_authenticated_user() -> None:
    app = create_app()
    app.dependency_overrides[require_current_principal] = lambda: AuthPrincipal(
        42, "alice", "token", frozenset({"user"})
    )
    records = RecordStub()
    app.dependency_overrides[get_interview_session_service] = lambda: SessionStub()
    app.dependency_overrides[get_interview_record_service] = lambda: records
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.put(
                "/api/xunzhi/v1/interview/sessions/session-1/finish",
                headers={"Authorization": "Bearer token"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.json()["code"] == "0"
    assert records.finalized == [("session-1", 42), ("session-1", 42)]


@pytest.mark.anyio
async def test_interview_conversations_route_returns_page() -> None:
    app = create_app()
    app.dependency_overrides[require_current_principal] = lambda: AuthPrincipal(
        42, "alice", "token", frozenset({"user"})
    )
    app.dependency_overrides[get_interview_session_service] = lambda: SessionStub()
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get(
                "/api/xunzhi/v1/interview/conversations",
                params={
                    "current": 2,
                    "size": 5,
                    "status": "FINISHED",
                    "keyword": "python",
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.json()["data"] == {
        "records": [],
        "current": 2,
        "size": 5,
        "total": 0,
    }


@pytest.mark.anyio
async def test_resume_extraction_returns_business_error_details() -> None:
    app = create_app()
    app.dependency_overrides[require_current_principal] = lambda: AuthPrincipal(
        42, "alice", "token", frozenset({"user"})
    )
    app.dependency_overrides[get_extraction_service] = lambda: ExtractionStub()
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/xunzhi/v1/interview/sessions/session-1/interview-questions",
                headers={"Authorization": "Bearer token"},
                files={"resumePdf": ("resume.pdf", b"pdf", "application/pdf")},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.json() == {
        "code": "B000001",
        "message": "interview workflow returned no questions",
        "data": None,
        "requestId": None,
    }
