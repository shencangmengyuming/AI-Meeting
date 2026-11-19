import pytest

from app.ai.application.chat import AiChatService
from app.ai.application.conversations import AiConversationService

from .test_conversations import Database


class Provider:
    async def stream(self, prompt, configuration, history):
        assert prompt == "question"
        yield ("reasoning_content", "thinking")
        yield ("content", "answer")


class Configurations:
    async def get_enabled(self, ai_id):
        return {"id": ai_id, "apiUrl": "https://provider.test", "modelName": "m"}


@pytest.mark.anyio
async def test_chat_persists_user_before_provider_and_assistant_after() -> None:
    database = Database()
    conversations = AiConversationService(database)
    created = await conversations.create("owner", 3, "hello")
    service = AiChatService(conversations, Configurations(), Provider())

    events = [
        item
        async for item in service.stream(
            str(created["sessionId"]), "owner", "question"
        )
    ]
    history = await conversations.history(str(created["sessionId"]), "owner")

    assert events == [
        ("reasoning_content", "thinking"),
        ("content", "answer"),
    ]
    assert [item["messageType"] for item in history] == [1, 2]
    assert history[-1]["reasoningContent"] == "thinking"
