import pytest

from app.ai.application.conversations import AiConversationService


class Collection:
    def __init__(self) -> None:
        self.documents: list[dict[str, object]] = []

    async def insert_one(self, document):
        self.documents.append(document)

    async def find_one(self, query):
        for item in self.documents:
            if all(item.get(k) == v for k, v in query.items()):
                return item
        return None

    async def update_one(self, query, update):
        item = await self.find_one(query)
        if item is not None:
            item.update(update.get("$set", {}))

    async def find(self, query):
        return [
            item
            for item in self.documents
            if all(item.get(k) == v for k, v in query.items())
        ]


class Database:
    def __init__(self) -> None:
        self.collections = {
            "ai_conversation": Collection(),
            "ai_message": Collection(),
        }

    def __getitem__(self, name):
        return self.collections[name]


@pytest.mark.anyio
async def test_ai_conversation_crud_enforces_owner() -> None:
    service = AiConversationService(Database())
    created = await service.create("owner", 3, "hello")
    await service.update(created["sessionId"], "owner", title="renamed")
    loaded = await service.get(created["sessionId"], "owner")
    await service.end(created["sessionId"], "owner")

    assert loaded["title"] == "renamed"
    with pytest.raises(PermissionError):
        await service.get(created["sessionId"], "other")


@pytest.mark.anyio
async def test_ai_messages_are_ordered_and_owned() -> None:
    database = Database()
    service = AiConversationService(database)
    created = await service.create("owner", 3, "hello")
    session_id = str(created["sessionId"])
    await service.append_message(session_id, "owner", "user", "one")
    await service.append_message(session_id, "owner", "assistant", "two")

    history = await service.history(session_id, "owner")

    assert [item["messageSeq"] for item in history] == [1, 2]
    assert [item["messageContent"] for item in history] == ["one", "two"]
