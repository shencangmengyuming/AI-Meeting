import importlib
from typing import Any

import pytest


def flow_module() -> Any:
    return importlib.import_module("app.interview.domain.flow")


def state(
    *,
    status: str = "ASKING",
    current_index: int = 0,
    current_question_number: str | None = "1",
    total_questions: int = 2,
    follow_up_count: int = 0,
) -> Any:
    flow = flow_module()
    return flow.InterviewFlowState(
        status=flow.InterviewFlowStatus(status),
        current_index=current_index,
        current_question_number=current_question_number,
        total_questions=total_questions,
        follow_up_count=follow_up_count,
        max_follow_up=2,
        version=1,
        total_score=0,
    )


def test_state_machine_rejects_transition_out_of_completed_state() -> None:
    flow = flow_module()
    machine = flow.InterviewFlowStateMachine()

    with pytest.raises(ValueError, match="COMPLETED -> EVALUATING"):
        machine.move_to_evaluating(state(status="COMPLETED"))


def test_start_follow_up_keeps_main_index_and_increments_count() -> None:
    flow = flow_module()
    machine = flow.InterviewFlowStateMachine()

    evaluating = machine.move_to_evaluating(state())
    follow_up = machine.start_follow_up(evaluating, "1-F1")

    assert follow_up.status is flow.InterviewFlowStatus.FOLLOW_UP
    assert follow_up.current_index == 0
    assert follow_up.current_question_number == "1-F1"
    assert follow_up.follow_up_count == 1
    assert follow_up.version == 3


def test_follow_up_answer_can_enter_evaluating_then_advance_main_question() -> None:
    flow = flow_module()
    machine = flow.InterviewFlowStateMachine()
    follow_up = state(
        status="FOLLOW_UP",
        current_question_number="1-F1",
        follow_up_count=1,
    )

    evaluating = machine.move_to_evaluating(follow_up)
    next_question = machine.advance_main_question(evaluating)

    assert next_question.status is flow.InterviewFlowStatus.ASKING
    assert next_question.current_index == 1
    assert next_question.current_question_number == "2"
    assert next_question.follow_up_count == 0


def test_advancing_last_question_marks_flow_completed() -> None:
    flow = flow_module()
    machine = flow.InterviewFlowStateMachine()
    last_question = state(
        status="EVALUATING",
        current_index=1,
        current_question_number="2",
    )

    completed = machine.advance_main_question(last_question)

    assert completed.status is flow.InterviewFlowStatus.COMPLETED
    assert completed.current_index == 1
    assert completed.current_question_number is None
    assert completed.follow_up_count == 0
    assert completed.finished is True


def test_flow_mapping_keeps_existing_python_cache_contract() -> None:
    flow = flow_module()
    restored = flow.InterviewFlowState.from_mapping(
        {
            "status": "FOLLOW_UP",
            "currentIndex": 0,
            "currentQuestionNumber": "1-F2",
            "totalQuestions": 3,
            "followUpCount": 2,
            "maxFollowUp": 2,
            "version": 7,
            "totalScore": 85,
            "finished": False,
        }
    )

    assert restored.to_mapping() == {
        "status": "FOLLOW_UP",
        "currentIndex": 0,
        "currentQuestionNumber": "1-F2",
        "totalQuestions": 3,
        "followUpCount": 2,
        "maxFollowUp": 2,
        "version": 7,
        "totalScore": 85,
        "finished": False,
    }
