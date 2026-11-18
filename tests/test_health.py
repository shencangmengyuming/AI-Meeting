import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app


@pytest.mark.anyio
async def test_health_returns_up() -> None:
    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/actuator/health")

    assert response.status_code == 200
    assert response.json() == {"status": "UP"}
