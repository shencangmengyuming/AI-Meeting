from fastapi import FastAPI

from app.core.exception_handlers import install_exception_handlers
from app.core.lifespan import lifespan


def create_app() -> FastAPI:
    app = FastAPI(title="AI Meeting Backend", lifespan=lifespan)
    install_exception_handlers(app)

    @app.get("/actuator/health")
    async def health() -> dict[str, str]:
        return {"status": "UP"}

    return app
