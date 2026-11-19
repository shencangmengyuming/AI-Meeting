import pytest


class Collection:
    def __init__(self) -> None:
        self.documents: list[dict[str, object]] = []

    async def insert_one(self, document: dict[str, object]) -> None:
        self.documents.append(document)

    async def find_one(self, query: dict[str, object]):
        matches = [
            item
            for item in self.documents
            if all(item.get(k) == v for k, v in query.items())
        ]
        return matches[0] if matches else None

    def find(self, query: dict[str, object]):
        documents = [
            item
            for item in self.documents
            if all(item.get(k) == v for k, v in query.items())
        ]

        class Cursor:
            async def to_list(self, length=None):
                del length
                return documents

        return Cursor()


class Database:
    def __init__(self) -> None:
        self.collections: dict[str, Collection] = {}

    def __getitem__(self, name: str) -> Collection:
        return self.collections.setdefault(name, Collection())


@pytest.mark.anyio
async def test_agent_session_persists_owned_messages() -> None:
    from app.agent.application.session import AgentSessionService

    service = AgentSessionService(Database())
    session = await service.create_session(7, agent_id=11, first_message="hello")
    await service.append_message(session.session_id, 7, "user", "hello")
    messages = await service.list_messages(session.session_id, 7)

    assert session.user_id == 7
    assert session.agent_id == 11
    assert session.title == "hello"
    assert await service.bound_agent_id(session.session_id, 7) == 11
    assert messages[0]["content"] == "hello"
    assert len(service.sessions.documents) == 1
    assert len(service.messages.documents) == 1


@pytest.mark.anyio
async def test_agent_session_rejects_other_owner() -> None:
    from app.agent.application.session import AgentSessionService

    service = AgentSessionService(Database())
    session = await service.create_session(7, agent_id=11)

    with pytest.raises(PermissionError):
        await service.list_messages(session.session_id, 8)
