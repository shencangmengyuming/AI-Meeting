import logging
from typing import Any, cast

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.errors import BusinessError
from app.core.result import failure

logger = logging.getLogger(__name__)


def _response(result: Any, status_code: int = 200) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=result.model_dump(by_alias=True),
    )


async def business_error_handler(_: Request, exc: BusinessError) -> JSONResponse:
    return _response(failure(exc.code, exc.message), exc.http_status)


async def validation_error_handler(
    _: Request, exc: RequestValidationError
) -> JSONResponse:
    errors = exc.errors()
    malformed = any(
        error.get("type") in {"json_invalid", "missing"} for error in errors
    )
    message = "请求体不能为空或格式错误" if malformed else str(errors[0].get("msg", ""))
    return _response(failure("A000001", message))


async def unexpected_error_handler(_: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled backend exception", exc_info=exc)
    return _response(failure())


def install_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(
        BusinessError, cast(Any, business_error_handler)
    )
    app.add_exception_handler(
        RequestValidationError, cast(Any, validation_error_handler)
    )
    app.add_exception_handler(Exception, unexpected_error_handler)
