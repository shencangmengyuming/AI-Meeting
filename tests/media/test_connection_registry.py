import pytest

from app.media.application.connection_registry import ConnectionRegistry


class Socket:
    def __init__(self) -> None:
        self.messages = []

    async def send_json(self, value):
        self.messages.append(value)


@pytest.mark.anyio
async def test_registry_routes_to_all_user_connections_and_cleans_up() -> None:
    registry = ConnectionRegistry()
    first, second = Socket(), Socket()
    await registry.add("7", "a", first)
    await registry.add("7", "b", second)

    delivered = await registry.push("7", {"type": "notice"})
    await registry.remove("7", "a")

    assert delivered == 2
    assert first.messages == [{"type": "notice"}]
    assert await registry.is_online("7") is True
    await registry.remove("7", "b")
    assert await registry.is_online("7") is False
