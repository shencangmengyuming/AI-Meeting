import asyncio
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, Request

from app.agent.application.service import AgentService
from app.agent.infrastructure.configuration import (
    CachedAgentConfigurationRepository,
    MySqlAgentConfigurationRepository,
)
from app.agent.infrastructure.file_assets import MySqlAgentFileRepository
from app.agent.infrastructure.providers.xunfei import XunfeiAgentProvider
from app.core.settings import Settings, get_settings
from app.infrastructure.http import create_http_client
from app.infrastructure.mongodb import create_mongo_resources
from app.infrastructure.mysql import create_mysql_resources
from app.infrastructure.redis import create_redis_resource
from app.infrastructure.schema import ensure_mysql_schema
from app.interview.infrastructure.indexes import ensure_interview_indexes
from app.media.application.connection_registry import ConnectionRegistry
from app.media.application.push_service import WebSocketPushService
from app.media.infrastructure.websocket_routing import WebSocketRouting
from app.media.infrastructure.xunfei_asr_client import XunfeiAsrConnectionFactory
from app.media.infrastructure.xunfei_tts import XunfeiTtsService
from app.workers.repair_agent_file_asset import run_agent_file_repair_worker
from app.workers.repair_interview_turn import run_turn_repair_worker


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
    settings = get_settings()
    resources = build_resources(settings)
    app.state.resources = resources
    await ensure_mysql_schema(resources.engine)
    if hasattr(resources.mongo_database, "__getitem__"):
        await ensure_interview_indexes(resources.mongo_database)
    agent_configurations = CachedAgentConfigurationRepository(
        MySqlAgentConfigurationRepository(resources.session_factory)
    )
    app.state.agent_configurations = agent_configurations
    app.state.agent_service = AgentService(
        XunfeiAgentProvider(
            agent_configurations,
            resources.http,
        )
    )
    registry = ConnectionRegistry()
    app.state.media_connections = registry
    routing = WebSocketRouting(resources.redis, f"node-{uuid4()}")
    app.state.websocket_push_service = WebSocketPushService(
        registry,
        routing,
    )
    configuration_pubsub = resources.redis.pubsub()
    media_pubsub = resources.redis.pubsub()
    await configuration_pubsub.subscribe("configuration:invalidation")
    await media_pubsub.subscribe(routing.node_channel)
    background_stop = asyncio.Event()
    configuration_task = asyncio.create_task(
        agent_configurations.consume_invalidations(
            configuration_pubsub, background_stop
        ),
        name="agent-configuration-invalidation",
    )
    media_task = asyncio.create_task(
        app.state.websocket_push_service.consume(media_pubsub, background_stop),
        name="media-websocket-routing",
    )
    turn_repair_task = asyncio.create_task(
        run_turn_repair_worker(
            resources.redis,
            resources.mongo_database,
            background_stop,
        ),
        name="interview-turn-repair",
    )
    agent_file_repair_task = asyncio.create_task(
        run_agent_file_repair_worker(
            resources.redis,
            MySqlAgentFileRepository(resources.session_factory),
            background_stop,
        ),
        name="agent-file-repair",
    )
    if (
        settings.xunfei_tts_app_id
        and settings.xunfei_tts_api_key
        and settings.xunfei_tts_api_secret
    ):
        app.state.tts_service = XunfeiTtsService(
            settings.xunfei_tts_app_id,
            settings.xunfei_tts_api_key,
            settings.xunfei_tts_api_secret,
            resources.http,
        )
    if (
        settings.xunfei_asr_app_id
        and settings.xunfei_asr_api_key
        and settings.xunfei_asr_api_secret
    ):
        app.state.asr_connection_factory = XunfeiAsrConnectionFactory(
            settings.xunfei_asr_app_id,
            settings.xunfei_asr_api_key,
            settings.xunfei_asr_api_secret,
        )
    try:
        yield
    finally:
        background_stop.set()
        configuration_task.cancel()
        media_task.cancel()
        turn_repair_task.cancel()
        agent_file_repair_task.cancel()
        for task in (
            configuration_task,
            media_task,
            turn_repair_task,
            agent_file_repair_task,
        ):
            with suppress(asyncio.CancelledError):
                await task
        await configuration_pubsub.unsubscribe("configuration:invalidation")
        await media_pubsub.unsubscribe(routing.node_channel)
        await configuration_pubsub.aclose()
        await media_pubsub.aclose()
        await close_resources(resources)


def get_resources(request: Request) -> AppResources:
    return request.app.state.resources
