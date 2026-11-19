import pytest

from app.interview.infrastructure.indexes import ensure_interview_indexes


class Collection:
    def __init__(self) -> None:
        self.calls = []

    async def create_index(self, keys, *, unique=False, name=None):
        self.calls.append((keys, unique, name))
        return name


class Database:
    def __init__(self) -> None:
        self.collections = {
            "interview_record": Collection(),
            "interview_turn": Collection(),
            "interview_runtime_snapshot": Collection(),
        }

    def __getitem__(self, name):
        return self.collections[name]


@pytest.mark.anyio
async def test_interview_indexes_protect_report_and_turn_identity() -> None:
    database = Database()

    await ensure_interview_indexes(database)

    assert database.collections["interview_record"].calls == [
        ([('sessionId', 1), ('userId', 1), ('delFlag', 1)], True,
         "uq_interview_record_session_user")
    ]
    assert database.collections["interview_turn"].calls == [
        ([('sessionId', 1), ('requestId', 1)], True,
         "uq_interview_turn_request")
    ]
    assert database.collections["interview_runtime_snapshot"].calls == [
        ([('sessionId', 1)], True, "uq_interview_runtime_snapshot_session")
    ]
