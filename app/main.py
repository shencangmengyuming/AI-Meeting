from fastapi import FastAPI

from app.agent.api.router import agents_router
from app.agent.api.router import router as agent_router
from app.ai.api.router import router as ai_router
from app.auth_user.api.router import router as auth_router
from app.auth_user.api.user_router import router as user_router
from app.configuration.api.router import router as configuration_router
from app.core.exception_handlers import install_exception_handlers
from app.core.lifespan import lifespan
from app.interview.api.router import router as interview_router
from app.media.api.management import router as media_management_router
from app.media.api.router import legacy_router as media_legacy_router
from app.media.api.router import router as media_router
from app.media.api.websocket import router as media_websocket_router


def create_app() -> FastAPI:
    app = FastAPI(title="AI Meeting Backend", lifespan=lifespan)
    install_exception_handlers(app)
    app.include_router(auth_router)
    app.include_router(user_router)
    app.include_router(agent_router)
    app.include_router(agents_router)
    app.include_router(ai_router)
    app.include_router(configuration_router)
    app.include_router(interview_router)
    app.include_router(media_router)
    app.include_router(media_legacy_router)
    app.include_router(media_management_router)
    app.include_router(media_websocket_router)

    @app.get("/actuator/health")
    async def health() -> dict[str, str]:
        return {"status": "UP"}

    return app
