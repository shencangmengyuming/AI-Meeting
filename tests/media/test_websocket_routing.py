import json

import pytest

from app.media.infrastructure.websocket_routing import WebSocketRouting


class Redis:
    def __init__(self) -> None:
        self.values = {}
        self.published = []

    async def set(self, key, value, ex=None): self.values[key] = value
    async def get(self, key): return self.values.get(key)
    async def delete(self, key): return int(self.values.pop(key, None) is not None)
    async def publish(self, channel, value) -> int:
        self.published.append((channel, value))
        return 1


@pytest.mark.anyio
async def test_websocket_routing_publishes_to_owning_node() -> None:
    redis = Redis()
    owner = WebSocketRouting(redis, "node-a")
    publisher = WebSocketRouting(redis, "node-b")
    await owner.register("7")

    delivered = await publisher.publish("7", {"type": "notice"})

    assert delivered == 1
    channel, raw = redis.published[0]
    assert channel == "media:ws:node:node-a"
    assert json.loads(raw)["envelope"] == {"type": "notice"}


@pytest.mark.anyio
async def test_websocket_routing_clears_stale_owner_without_subscriber() -> None:
    redis = Redis()
    owner = WebSocketRouting(redis, "node-a")
    publisher = WebSocketRouting(redis, "node-b")
    await owner.register("7")

    async def no_subscribers(channel, value) -> int:
        redis.published.append((channel, value))
        return 0

    redis.publish = no_subscribers

    delivered = await publisher.publish("7", {"type": "notice"})

    assert delivered == 0
    assert await publisher.owner("7") is None
