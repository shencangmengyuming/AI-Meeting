import pytest

from app.interview.application.session import InterviewSessionService


class Collection:
    def __init__(self, document=None):
        self.document = document

    async def find_one(self, query, projection=None):
        return self.document


class Database:
    def __init__(self):
        self.collections = {
            "interview_session": Collection(
                {
                    "sessionId": "s1",
                    "userId": 7,
                    "status": "READY",
                    "resumeUrl": "https://resume",
                    "interviewType": "backend",
                    "delFlag": 0,
                }
            ),
            "interview_question": Collection(
                {
                    "sessionId": "s1",
                    "resumeScore": 86,
                    "suggestions": ["locks", "retry"],
                }
            ),
        }

    def __getitem__(self, name):
        return self.collections[name]


@pytest.mark.anyio
async def test_restore_returns_java_compatible_resume_metadata() -> None:
    service = InterviewSessionService(Database())  # type: ignore[arg-type]

    restored = await service.restore("s1", 7)

    assert restored["canResume"] is True
    assert restored["resumeFileUrl"] == "https://resume"
    assert restored["resumeScore"] == 86
    assert restored["suggestions"] == {"1": "locks", "2": "retry"}
