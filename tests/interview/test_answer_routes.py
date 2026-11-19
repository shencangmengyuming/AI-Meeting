import pytest
from httpx import ASGITransport, AsyncClient

from app.auth_user.api.dependencies import require_current_principal
from app.auth_user.domain.session import AuthPrincipal
from app.interview.api.router import get_interview_answer_service
from app.main import create_app


class AnswerStub:
    async def submit(self, *args: object):
        return {
            "questionNumber": "1",
            "questionContent": "First",
            "isSuccess": True,
            "finished": False,
            "nextQuestionNumber": "2",
            "nextQuestion": "Second",
        }


@pytest.mark.anyio
async def test_answer_json_submits_for_authenticated_user() -> None:
    app = create_app()
    app.dependency_overrides[require_current_principal] = lambda: AuthPrincipal(
        42, "alice", "token", frozenset({"user"})
    )
    app.dependency_overrides[get_interview_answer_service] = lambda: AnswerStub()
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/xunzhi/v1/interview/sessions/session-1/interview/answer-json",
                headers={"Authorization": "Bearer token"},
                json={
                    "questionNumber": "1",
                    "answerContent": "My answer",
                    "requestId": "request-1",
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.json()["data"]["nextQuestionNumber"] == "2"


@pytest.mark.anyio
async def test_answer_form_uses_the_same_pipeline() -> None:
    app = create_app()
    app.dependency_overrides[require_current_principal] = lambda: AuthPrincipal(
        42, "alice", "token", frozenset({"user"})
    )
    app.dependency_overrides[get_interview_answer_service] = lambda: AnswerStub()
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/xunzhi/v1/interview/sessions/session-1/interview/answer",
                data={
                    "questionNumber": "1",
                    "answerContent": "My answer",
                    "requestId": "request-1",
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["data"]["nextQuestionNumber"] == "2"
