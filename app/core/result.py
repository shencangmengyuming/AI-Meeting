from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class Result(BaseModel, Generic[T]):
    model_config = ConfigDict(populate_by_name=True)

    code: str
    message: str | None = None
    data: T | None = None
    request_id: str | None = Field(default=None, alias="requestId")


def success(data: T | None = None) -> Result[T]:
    return Result(code="0", data=data)


def failure(code: str = "B000001", message: str = "系统执行出错") -> Result[None]:
    return Result(code=code, message=message)
