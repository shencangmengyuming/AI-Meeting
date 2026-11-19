from dataclasses import dataclass

import pytest


def test_scene_resolver_prefers_bound_alias_and_masks_secrets() -> None:
    from app.agent.domain.configuration import AgentConfiguration, BusinessAgentScene

    configuration = AgentConfiguration(
        agent_id=7,
        name="面试提问官",
        api_key="secret-key",
        api_secret="secret-value",
        flow_id="flow-7",
    )
    resolved = BusinessAgentScene("follow_up", aliases=("追问",)).resolve(
        {"追问": configuration}
    )

    assert resolved.name == "面试提问官"
    assert resolved.masked_api_key == "secr****key"
    assert resolved.to_public_dict()["apiSecret"] is None


@pytest.mark.anyio
async def test_stream_encoder_emits_ordered_content_and_done_events() -> None:
    from app.agent.application.streaming import AgentStreamEncoder, StreamEvent

    encoded = list(
        AgentStreamEncoder().encode(
            [
                StreamEvent("content", "hello"),
                StreamEvent("content", " world"),
                StreamEvent("done", None),
            ]
        )
    )

    assert encoded == [
        "event: content\ndata: hello\n\n",
        "event: content\ndata:  world\n\n",
        "event: done\ndata: {}\n\n",
    ]


@dataclass
class ProviderStub:
    async def complete(self, prompt: str, *, stream: bool = False):
        assert prompt == "hi"
        assert stream is True
        return ["hello", " world"]


@pytest.mark.anyio
async def test_agent_service_delegates_to_provider_without_exposing_credentials(
) -> None:
    from app.agent.application.service import AgentService

    events = [item async for item in AgentService(ProviderStub()).stream("hi")]

    assert [event.data for event in events] == ["hello", " world", None]
    assert events[-1].kind == "done"
