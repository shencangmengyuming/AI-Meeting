from typing import Any


async def ensure_interview_indexes(database: Any) -> None:
    """Create the uniqueness boundaries required by replay and finalization."""
    await database["interview_record"].create_index(
        [("sessionId", 1), ("userId", 1), ("delFlag", 1)],
        unique=True,
        name="uq_interview_record_session_user",
    )
    await database["interview_turn"].create_index(
        [("sessionId", 1), ("requestId", 1)],
        unique=True,
        name="uq_interview_turn_request",
    )
    await database["interview_runtime_snapshot"].create_index(
        [("sessionId", 1)],
        unique=True,
        name="uq_interview_runtime_snapshot_session",
    )
