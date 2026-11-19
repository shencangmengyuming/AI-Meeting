from dataclasses import dataclass
from typing import Any
from urllib.parse import unquote

import httpx


class ResumePreviewSourceError(ValueError):
    pass


class ResumePreviewDownloadError(RuntimeError):
    pass


@dataclass(frozen=True)
class ResumePreviewResource:
    content: bytes
    content_type: str
    filename: str


class InterviewResumePreviewService:
    def __init__(self, database: Any, http: Any) -> None:
        self.database = database
        self.http = http

    async def load(
        self, session_id: str, user_id: int
    ) -> ResumePreviewResource:
        session = await self.database["interview_session"].find_one(
            {"sessionId": session_id, "userId": user_id, "delFlag": 0}
        )
        if session is None:
            raise ResumePreviewSourceError("Interview session does not exist")
        question = await self.database["interview_question"].find_one(
            {"sessionId": session_id, "delFlag": 0}
        )
        source = None
        if question:
            source = question.get("resumeUrl") or question.get("resumeFileUrl")
        source = source or session.get("resumeUrl") or session.get("resumeFileUrl")
        if not isinstance(source, str) or not source.strip():
            raise ResumePreviewSourceError("Resume preview source is missing")
        source = source.strip()
        _validate_source(source)
        try:
            response = await self.http.get(source, follow_redirects=False)
        except Exception as exc:
            raise ResumePreviewDownloadError(
                f"Failed to download resume preview: {type(exc).__name__}"
            ) from exc
        if response.status_code < 200 or response.status_code >= 300:
            raise ResumePreviewDownloadError(
                "Failed to download resume preview, "
                f"HTTP status: {response.status_code}"
            )
        content = bytes(response.content)
        if not content:
            raise ResumePreviewDownloadError(
                "Failed to download resume preview: empty content"
            )
        filename = unquote(httpx.URL(source).path.split("/")[-1]).strip()
        if not filename:
            filename = f"resume-{session_id}.pdf"
        elif not filename.lower().endswith(".pdf"):
            filename += ".pdf"
        response_type = str(response.headers.get("content-type") or "").split(
            ";", 1
        )[0]
        content_type = (
            "application/pdf"
            if content.startswith(b"%PDF-")
            else response_type or "application/octet-stream"
        )
        return ResumePreviewResource(content, content_type, filename)


def _validate_source(source: str) -> None:
    url = httpx.URL(source)
    host = (url.host or "").lower()
    trusted = host == "xf-yun.com" or host.endswith(".xf-yun.com")
    trusted = trusted or host == "iflyaisol.com" or host.endswith(
        ".iflyaisol.com"
    )
    if url.scheme != "https" or not trusted:
        raise ResumePreviewSourceError("Resume preview source is not trusted")
