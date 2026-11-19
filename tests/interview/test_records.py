import pytest
from httpx import ASGITransport, AsyncClient

from app.auth_user.api.dependencies import require_current_principal
from app.auth_user.domain.session import AuthPrincipal
from app.interview.api.router import get_interview_record_service
from app.interview.application.records import InterviewRecordService
from app.main import create_app


class Collection:
    def __init__(self, documents=None):
        self.documents = documents or []

    async def find_one(self, query):
        return next(
            (
                item
                for item in self.documents
                if all(item.get(k) == v for k, v in query.items())
            ),
            None,
        )

    async def insert_one(self, document):
        self.documents.append(document)

    async def update_one(self, query, update, upsert=False):
        existing = await self.find_one(query)
        if existing is not None:
            existing.update(update.get("$set", {}))
        elif upsert:
            self.documents.append({**query, **update.get("$setOnInsert", {})})

    async def find(self, query):
        return [
            item
            for item in self.documents
            if all(item.get(k) == v for k, v in query.items())
        ]


class AtomicRecordCollection(Collection):
    def __init__(self, documents=None):
        super().__init__(documents)
        self.upserts = 0

    async def update_one(self, query, update, upsert=False):
        self.upserts += 1
        return await super().update_one(query, update, upsert=upsert)

class Database:
    def __init__(self):
        self.collections = {
            "interview_turn": Collection([
                {
                    "sessionId": "s1", "userId": 7, "requestId": "r2",
                    "questionNumber": "2", "score": 60, "feedback": "ok",
                    "missingPoints": ["retry"], "createTime": "2026-01-02",
                },
                {
                    "sessionId": "s1", "userId": 7, "requestId": "r1",
                    "questionNumber": "1", "score": 80, "feedback": "good",
                    "missingPoints": [], "createTime": "2026-01-01",
                },
            ]),
            "interview_record": Collection(),
            "interview_session": Collection([
                {
                    "sessionId": "s1",
                    "userId": 7,
                    "status": "FINISHED",
                    "interviewType": "backend",
                    "delFlag": 0,
                }
            ]),
            "interview_question": Collection([
                {
                    "sessionId": "s1",
                    "questions": ["Q1", "Q2"],
                    "resumeScore": 86,
                    "suggestions": ["retry"],
                    "interviewType": "backend",
                    "delFlag": 0,
                }
            ]),
        }
    def __getitem__(self, name):
        return self.collections[name]


@pytest.mark.anyio
async def test_finalize_record_is_idempotent_and_aggregates_turns() -> None:
    database = Database()
    service = InterviewRecordService(database)

    first = await service.finalize("s1", 7)
    second = await service.finalize("s1", 7)

    assert first["interviewScore"] == 70
    assert second == first
    assert len(database.collections["interview_record"].documents) == 1
    assert [item["requestId"] for item in first["playbackItems"]] == ["r1", "r2"]
    assert first["reviewFeedback"]["improvementTips"] == ["retry"]
    assert first["resumeScore"] == 86
    assert first["questionCount"] == 2
    assert first["interviewStatus"] == "FINISHED"
    assert first["interviewSuggestionsMap"] == {"1": "retry"}


@pytest.mark.anyio
async def test_save_and_page_records_are_owned_and_filterable() -> None:
    database = Database()
    service = InterviewRecordService(database)

    await service.save(
        "s2",
        7,
        {
            "interviewScore": 91,
            "interviewSuggestions": "keep going",
            "interviewDirection": "backend",
        },
    )
    page = await service.page(
        7, current=1, size=10, min_score=90, direction="back"
    )

    assert page["total"] == 1
    assert page["records"][0]["sessionId"] == "s2"


@pytest.mark.anyio
async def test_finalize_uses_atomic_upsert_for_concurrent_callers() -> None:
    database = Database()
    database.collections["interview_record"] = AtomicRecordCollection()
    service = InterviewRecordService(database)

    first, second = await __import__("asyncio").gather(
        service.finalize("s1", 7), service.finalize("s1", 7)
    )

    assert first == second
    assert len(database.collections["interview_record"].documents) == 1
    assert database.collections["interview_record"].upserts >= 1


class RecordStub:
    def __init__(self) -> None:
        self.saved = []

    async def save(self, session_id, user_id, values):
        self.saved.append((session_id, user_id, values))

    async def page(self, user_id, **filters):
        assert user_id == 7
        return {"records": [], "current": 1, "size": 10, "total": 0}


@pytest.mark.anyio
async def test_record_save_and_page_routes_match_java_paths() -> None:
    app = create_app()
    records = RecordStub()
    app.dependency_overrides[require_current_principal] = lambda: AuthPrincipal(
        7, "owner", "token", frozenset({"user"})
    )
    app.dependency_overrides[get_interview_record_service] = lambda: records
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            saved = await client.post(
                "/api/xunzhi/v1/interview/interview/record",
                json={
                    "sessionId": "s1",
                    "interviewScore": 90,
                    "interviewDirection": "backend",
                },
            )
            page = await client.get(
                "/api/xunzhi/v1/interview/interview/records",
                params={"pageNum": 1, "pageSize": 10, "minScore": 80},
            )
    finally:
        app.dependency_overrides.clear()

    assert saved.status_code == 200
    assert records.saved[0][0:2] == ("s1", 7)
    assert page.json()["data"]["total"] == 0
