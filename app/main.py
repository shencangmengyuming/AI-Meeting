from fastapi import FastAPI


def create_app() -> FastAPI:
    app = FastAPI(title="AI Meeting Backend")

    @app.get("/actuator/health")
    async def health() -> dict[str, str]:
        return {"status": "UP"}

    return app
