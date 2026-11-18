from typing import Annotated

import pytest
from fastapi import Body, FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.errors import BusinessError
from app.core.exception_handlers import install_exception_handlers


@pytest.fixture
def validation_app() -> FastAPI:
    app = FastAPI()
    install_exception_handlers(app)

    @app.post("/payload")
    async def payload(value: Annotated[str, Body(min_length=3)]) -> dict[str, str]:
        return {"value": value}

    @app.get("/business-error")
    async def business_error() -> None:
        raise BusinessError("B000001", "business failed")

    return app


@pytest.mark.anyio
async def test_malformed_json_uses_java_client_error_contract(
    validation_app: FastAPI,
) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=validation_app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/payload", content="{", headers={"content-type": "application/json"}
        )

    assert response.status_code == 200
    assert response.json() == {
        "code": "A000001",
        "message": "请求体不能为空或格式错误",
        "data": None,
        "requestId": None,
    }


@pytest.mark.anyio
async def test_validation_uses_first_error_message(
    validation_app: FastAPI,
) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=validation_app), base_url="http://test"
    ) as client:
        response = await client.post("/payload", json="x")

    assert response.status_code == 200
    assert response.json()["code"] == "A000001"
    assert response.json()["message"]


@pytest.mark.anyio
async def test_business_error_uses_java_result_wrapper(
    validation_app: FastAPI,
) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=validation_app), base_url="http://test"
    ) as client:
        response = await client.get("/business-error")

    assert response.status_code == 200
    assert response.json() == {
        "code": "B000001",
        "message": "business failed",
        "data": None,
        "requestId": None,
    }
