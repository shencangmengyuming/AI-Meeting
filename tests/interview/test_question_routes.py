import pytest
from httpx import ASGITransport, AsyncClient

from app.auth_user.api.dependencies import require_current_principal
from app.auth_user.domain.session import AuthPrincipal
from app.interview.api.router import (
    get_interview_question_service,
    get_interview_report_service,
)
from app.main import create_app


class QuestionStub:
    async def get_questions(self, session_id: str, user_id: int) -> dict[str, str]:
        return {"1": "Tell me about Python", "2": "Explain asyncio"}

    async def get_first_question(self, session_id: str, user_id: int):
        return {
            "questionNumber": "1",
            "questionContent": "Tell me about Python",
            "isSuccess": True,
            "finished": False,
        }


class ReportStub:
    async def playback(self, session_id, user_id):
        assert (session_id, user_id) == ("session-1", 42)
        return [{"requestId": "r1", "questionNumber": "1"}]

    async def resume_score(self, session_id, user_id):
        assert (session_id, user_id) == ("session-1", 42)
        return 88

    async def suggestions(self, session_id, user_id):
        assert (session_id, user_id) == ("session-1", 42)
        return ["locks", "retry"]


@pytest.mark.anyio
async def test_question_routes_require_session_owner_context() -> None:
    app = create_app()
    app.dependency_overrides[require_current_principal] = lambda: AuthPrincipal(
        42, "alice", "token", frozenset({"user"})
    )
    app.dependency_overrides[get_interview_question_service] = lambda: QuestionStub()
    app.dependency_overrides[get_interview_report_service] = lambda: ReportStub()
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            list_response = await client.get(
                "/api/xunzhi/v1/interview/sessions/session-1/interview/questions",
                headers={"Authorization": "Bearer token"},
            )
            current_response = await client.get(
                "/api/xunzhi/v1/interview/sessions/session-1/current-question",
                headers={"Authorization": "Bearer token"},
            )
            messages_response = await client.get(
                "/api/xunzhi/v1/interview/conversations/session-1/messages"
            )
            history_response = await client.get(
                "/api/xunzhi/v1/interview/messages/history",
                params={"sessionId": "session-1", "current": 1, "size": 10},
            )
            resume_score_response = await client.get(
                "/api/xunzhi/v1/interview/sessions/session-1/resume/score"
            )
            suggestions_response = await client.get(
                "/api/xunzhi/v1/interview/sessions/session-1/interview/suggestions"
            )
    finally:
        app.dependency_overrides.clear()

    assert list_response.json()["data"]["2"] == "Explain asyncio"
    assert current_response.json()["data"]["questionNumber"] == "1"
    assert messages_response.json()["data"][0]["requestId"] == "r1"
    assert history_response.json()["data"]["total"] == 1
    assert resume_score_response.json()["data"] == 88
    assert suggestions_response.json()["data"] == {"1": "locks", "2": "retry"}
