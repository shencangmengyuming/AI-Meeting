import json
from typing import Any

DELETE_OWNER_SCRIPT = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('DEL', KEYS[1])
end
return 0
"""


class WebSocketRouting:
    def __init__(self, redis: Any, node_id: str, *, ttl_seconds: int = 60) -> None:
        self.redis = redis
        self.node_id = node_id
        self.ttl_seconds = ttl_seconds

    @property
    def node_channel(self) -> str:
        return f"media:ws:node:{self.node_id}"

    async def register(self, user_id: str) -> None:
        await self.redis.set(
            f"media:ws:owner:{user_id}",
            self.node_id,
            ex=self.ttl_seconds,
        )

    async def unregister(self, user_id: str) -> None:
        key = f"media:ws:owner:{user_id}"
        owner = await self.redis.get(key)
        if isinstance(owner, bytes):
            owner = owner.decode()
        if owner == self.node_id:
            await self.redis.delete(key)

    async def owner(self, user_id: str) -> str | None:
        value = await self.redis.get(f"media:ws:owner:{user_id}")
        if isinstance(value, bytes):
            return value.decode()
        return str(value) if value else None

    async def publish(self, user_id: str, envelope: dict[str, Any]) -> int:
        owner = await self.owner(user_id)
        if owner is None:
            return 0
        delivered = int(
            await self.redis.publish(
                f"media:ws:node:{owner}",
                json.dumps({"userId": user_id, "envelope": envelope}),
            )
        )
        if delivered == 0:
            await self.clear_owner(user_id, owner)
        return delivered

    async def clear_owner(self, user_id: str, expected_owner: str) -> None:
        key = f"media:ws:owner:{user_id}"
        eval_command = getattr(self.redis, "eval", None)
        if eval_command is not None:
            await eval_command(DELETE_OWNER_SCRIPT, 1, key, expected_owner)
            return
        owner = await self.owner(user_id)
        if owner == expected_owner:
            await self.redis.delete(key)
