import pytest
from httpx import ASGITransport, AsyncClient

from app.ai.api.router import get_ai_chat_service, get_ai_conversation_service
from app.auth_user.api.dependencies import require_current_principal
from app.auth_user.domain.session import AuthPrincipal
from app.main import create_app


class Conversations:
    async def create(self, username, ai_id, first_message):
        return {"sessionId": "s1", "aiId": ai_id, "title": first_message}

    async def page(self, username, current=1, size=10):
        return {"records": [], "current": current, "size": size, "total": 0}

    async def get(self, session_id, username):
        return {"sessionId": session_id, "username": username}

    async def update(self, session_id, username, **values): pass
    async def end(self, session_id, username): pass
    async def delete(self, session_id, username): pass
    async def history(self, session_id, username): return []
    async def history_page(self, username, **values): return {"records": []}


class Chat:
    async def stream(self, session_id, username, prompt):
        yield ("content", "hello")


@pytest.mark.anyio
async def test_ai_routes_create_and_stream_with_ai_sse_contract() -> None:
    app = create_app()
    app.dependency_overrides[require_current_principal] = lambda: AuthPrincipal(
        1, "owner", "token", frozenset({"user"})
    )
    app.dependency_overrides[get_ai_conversation_service] = lambda: Conversations()
    app.dependency_overrides[get_ai_chat_service] = lambda: Chat()
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            created = await client.post(
                "/api/xunzhi/v1/ai/conversations",
                json={"aiId": 3, "firstMessage": "demo"},
            )
            streamed = await client.post(
                "/api/xunzhi/v1/ai/sessions/s1/chat",
                json={"message": "hi"},
            )
            history_page = await client.get("/api/xunzhi/v1/ai/history/page")
    finally:
        app.dependency_overrides.clear()

    assert created.json()["data"]["sessionId"] == "s1"
    assert streamed.text == 'data: {"type":"content","content":"hello"}\n\n'
    assert "event: end" not in streamed.text
    assert history_page.json()["data"] == {"records": []}
