import pytest
from httpx import ASGITransport, AsyncClient

from app.auth_user.api.dependencies import require_current_principal
from app.auth_user.domain.session import AuthPrincipal
from app.interview.api.router import get_resume_preview_service
from app.interview.application.resume_preview import (
    InterviewResumePreviewService,
    ResumePreviewDownloadError,
    ResumePreviewSourceError,
)
from app.main import create_app


class Collection:
    def __init__(self, document=None):
        self.document = document

    async def find_one(self, query):
        return self.document


class Database:
    def __init__(self, question=None, session=None):
        self.collections = {
            "interview_question": Collection(question),
            "interview_session": Collection(session),
        }

    def __getitem__(self, name):
        return self.collections[name]


class Response:
    def __init__(self, status_code=200, content=b"%PDF-document", content_type="x"):
        self.status_code = status_code
        self.content = content
        self.headers = {"content-type": content_type}


class Http:
    def __init__(self, response=None):
        self.response = response or Response()
        self.urls = []

    async def get(self, url, *, follow_redirects=False):
        self.urls.append((url, follow_redirects))
        return self.response


@pytest.mark.anyio
async def test_resume_preview_downloads_owned_pdf_with_safe_filename() -> None:
    http = Http()
    service = InterviewResumePreviewService(
        Database(
            question={
                "sessionId": "s1",
                "resumeUrl": "https://xingchen-api.xf-yun.com/files/my%20cv",
            },
            session={"sessionId": "s1", "userId": 7, "delFlag": 0},
        ),
        http,
    )

    resource = await service.load("s1", 7)

    assert resource.content == b"%PDF-document"
    assert resource.content_type == "application/pdf"
    assert resource.filename == "my cv.pdf"
    assert http.urls == [
        ("https://xingchen-api.xf-yun.com/files/my%20cv", False)
    ]


@pytest.mark.anyio
async def test_resume_preview_rejects_untrusted_source_before_request() -> None:
    http = Http()
    service = InterviewResumePreviewService(
        Database(
            question={"sessionId": "s1", "resumeUrl": "http://127.0.0.1/a.pdf"},
            session={"sessionId": "s1", "userId": 7, "delFlag": 0},
        ),
        http,
    )

    with pytest.raises(ResumePreviewSourceError):
        await service.load("s1", 7)

    assert http.urls == []


@pytest.mark.anyio
async def test_resume_preview_maps_provider_failure() -> None:
    service = InterviewResumePreviewService(
        Database(
            question={
                "sessionId": "s1",
                "resumeUrl": "https://xingchen-api.xf-yun.com/files/a.pdf",
            },
            session={"sessionId": "s1", "userId": 7, "delFlag": 0},
        ),
        Http(Response(status_code=503)),
    )

    with pytest.raises(ResumePreviewDownloadError, match="HTTP status: 503"):
        await service.load("s1", 7)


class PreviewStub:
    async def load(self, session_id, user_id):
        assert (session_id, user_id) == ("s1", 7)
        from app.interview.application.resume_preview import ResumePreviewResource

        return ResumePreviewResource(b"%PDF-test", "application/pdf", "简历.pdf")


@pytest.mark.anyio
async def test_resume_preview_route_sets_inline_no_store_headers() -> None:
    app = create_app()
    app.dependency_overrides[require_current_principal] = lambda: AuthPrincipal(
        7, "owner", "token", frozenset({"user"})
    )
    app.dependency_overrides[get_resume_preview_service] = lambda: PreviewStub()
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get(
                "/api/xunzhi/v1/interview/sessions/s1/resume/preview"
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.content == b"%PDF-test"
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["cache-control"] == "no-store, must-revalidate"
    assert response.headers["pragma"] == "no-cache"
    assert "filename*=UTF-8''" in response.headers["content-disposition"]
