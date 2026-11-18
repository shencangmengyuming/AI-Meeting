from redis.asyncio import Redis


def create_redis_resource(redis_url: str) -> Redis:
    return Redis.from_url(redis_url, decode_responses=False)
