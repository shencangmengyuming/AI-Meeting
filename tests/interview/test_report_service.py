import pytest

from app.interview.application.reports import InterviewReportService


class Collection:
    async def find_one(self, query):
        return None

    async def find(self, query):
        return [
            {
                "requestId": "r2",
                "score": 60,
                "feedback": "brief",
                "missingPoints": ["locks", "retry"],
                "createTime": "2026-01-01T00:00:02Z",
            },
            {
                "requestId": "r1",
                "score": 80,
                "feedback": "clear",
                "missingPoints": ["locks"],
                "createTime": "2026-01-01T00:00:01Z",
            },
        ]


class SessionCollection:
    async def find_one(self, query):
        return {
            "sessionId": query["sessionId"],
            "userId": query["userId"],
            "delFlag": 0,
        }


class Database:
    def __getitem__(self, name):
        return SessionCollection() if name == "interview_session" else Collection()


@pytest.mark.anyio
async def test_report_service_aggregates_score_suggestions_and_radar() -> None:
    service = InterviewReportService(Database())
    assert await service.score("s", 1) == 70
    assert await service.suggestions("s", 1) == ["locks", "retry"]
    assert await service.radar("s", 1) == {
        "resumeScore": 0,
        "interviewPerformance": 70,
        "demeanorEvaluation": 0,
        "professionalSkills": 70,
        "potentialIndex": 70,
    }
    assert [item["requestId"] for item in await service.playback("s", 1)] == [
        "r1",
        "r2",
    ]


class Redis:
    async def get(self, key):
        assert key == "interview:resume:score:s"
        return b"86"


@pytest.mark.anyio
async def test_report_service_reads_resume_score_from_runtime_cache() -> None:
    service = InterviewReportService(Database(), Redis())

    assert await service.resume_score("s", 1) == 86
