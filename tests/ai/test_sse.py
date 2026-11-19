from app.ai.application.sse import encode_ai_event


def test_ai_sse_uses_data_only_frames_and_no_agent_end_event() -> None:
    assert encode_ai_event("content", "hello") == (
        'data: {"type":"content","content":"hello"}\n\n'
    )
    assert encode_ai_event("reasoning_content", "think") == (
        'data: {"type":"reasoning_content","content":"think"}\n\n'
    )
