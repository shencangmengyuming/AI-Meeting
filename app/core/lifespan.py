from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI, Request

from app.core.settings import Settings, get_settings
from app.infrastructure.http import create_http_client
from app.infrastructure.mongodb import create_mongo_resources
from app.infrastructure.mysql import create_mysql_resources
from app.infrastructure.redis import create_redis_resource


@dataclass(frozen=True)
class AppResources:
    engine: Any
    session_factory: Any
    mongo_client: Any
    mongo_database: Any
    redis: Any
    http: Any


def build_resources(settings: Settings) -> AppResources:
    engine, session_factory = create_mysql_resources(settings.database_url)
    mongo_client, mongo_database = create_mongo_resources(
        settings.mongo_url, settings.mongo_database
    )
    redis = create_redis_resource(settings.redis_url)
    http = create_http_client(
        settings.http_connect_timeout,
        settings.http_read_timeout,
        settings.http_write_timeout,
        settings.http_pool_timeout,
    )
    return AppResources(
        engine=engine,
        session_factory=session_factory,
        mongo_client=mongo_client,
        mongo_database=mongo_database,
        redis=redis,
        http=http,
    )


async def close_resources(resources: AppResources) -> None:
    await resources.engine.dispose()
    await resources.mongo_client.close()
    await resources.redis.aclose()
    await resources.http.aclose()


@asynccontextmanager
async def lifespan(app: FastAPI):
    resources = build_resources(get_settings())
    app.state.resources = resources
    try:
        yield
    finally:
        await close_resources(resources)


def get_resources(request: Request) -> AppResources:
    return request.app.state.resources
