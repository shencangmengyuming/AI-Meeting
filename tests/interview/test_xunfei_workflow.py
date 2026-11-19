import json
from typing import Any

import httpx
import pytest

from app.agent.domain.configuration import AgentConfiguration
from app.interview.infrastructure.workflow import XunfeiInterviewWorkflow, _structured


@pytest.mark.anyio
async def test_workflow_sends_resume_as_user_file() -> None:
    captured: dict[str, Any] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"questions": ["Q1"]})

    configuration = AgentConfiguration(
        agent_id=8,
        name="面试出题官",
        api_key="api-key",
        api_secret="api-secret",
        flow_id="flow-id",
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        workflow = XunfeiInterviewWorkflow(client)
        await workflow.invoke(
            configuration,
            "extract questions",
            "https://xingchen-api.xf-yun.com/resume.pdf",
            "session-1",
        )

    assert captured["body"]["parameters"] == {
        "AGENT_USER_INPUT": "extract questions",
        "USER_FILE": "https://xingchen-api.xf-yun.com/resume.pdf",
    }


def test_workflow_unwraps_delta_content_json() -> None:
    payload = {
        "code": 0,
        "choices": [
            {
                "delta": {
                    "content": '```json\n{"questions":["Q1"],"resumeScore":88}\n```'
                }
            }
        ],
    }

    assert _structured(payload) == {"questions": ["Q1"], "resumeScore": 88}
