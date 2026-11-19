import pytest
from httpx import ASGITransport, AsyncClient

from app.agent.application.session import AgentSessionService
from app.agent.domain.configuration import AgentConfiguration
from app.auth_user.api.dependencies import require_current_principal
from app.auth_user.domain.session import AuthPrincipal
from app.main import create_app


class Collection:
    def __init__(self) -> None:
        self.documents: list[dict[str, object]] = []

    async def insert_one(self, document):
        self.documents.append(document)

    async def find(self, query):
        return [
            item
            for item in self.documents
            if all(item.get(k) == v for k, v in query.items())
        ]

    async def update_one(self, query, update):
        for item in self.documents:
            if all(item.get(k) == v for k, v in query.items()):
                item.update(update.get("$set", {}))


class Database:
    def __init__(self) -> None:
        self.collections = {}

    def __getitem__(self, name):
        return self.collections.setdefault(name, Collection())


class Configurations:
    async def resolve(self, scene, aliases=()):
        assert scene == "GENERAL_AGENT_CHAT"
        return AgentConfiguration(7, "general", "key", "secret", "flow")


@pytest.mark.anyio
async def test_agent_session_create_history_and_end_routes() -> None:
    app = create_app()
    sessions = AgentSessionService(Database())
    app.state.agent_session_service = sessions
    app.state.agent_configurations = Configurations()
    app.dependency_overrides[require_current_principal] = lambda: AuthPrincipal(
        7, "user", "token", frozenset({"user"})
    )
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            created = await client.post(
                "/api/xunzhi/v1/agents/sessions", json={"firstMessage": "demo"}
            )
            session_id = created.json()["data"]["sessionId"]
            await client.post(
                f"/api/xunzhi/v1/agents/sessions/{session_id}/messages",
                json={"role": "user", "content": "hello"},
            )
            history = await client.get(
                f"/api/xunzhi/v1/agents/conversations/{session_id}/messages"
            )
            history_page = await client.get(
                "/api/xunzhi/v1/agents/messages/history",
                params={"sessionId": session_id, "current": 1, "size": 10},
            )
            ended = await client.put(
                f"/api/xunzhi/v1/agents/conversations/{session_id}/end"
            )
    finally:
        app.dependency_overrides.clear()

    assert created.status_code == 200
    assert created.json()["data"]["title"] == "demo"
    assert sessions.sessions.documents[0]["agentId"] == 7
    assert history.json()["data"][0]["content"] == "hello"
    assert history_page.json()["data"]["records"][0]["content"] == "hello"
    assert ended.status_code == 200
