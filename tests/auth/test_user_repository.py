from contextlib import asynccontextmanager
from typing import Any, cast

import pytest

from app.auth_user.infrastructure.user_repository import MySqlUserRepository


class Result:
    def __init__(self, rows):
        self.rows = rows

    def mappings(self):
        return self

    def first(self):
        return self.rows[0] if self.rows else None

    def all(self):
        return self.rows


class Session:
    def __init__(self, rows):
        self.rows = rows
        self.params = None

    async def execute(self, statement, params):
        self.params = params
        return Result(self.rows)

    async def commit(self):
        pass


class Factory:
    def __init__(self, rows):
        self.session = Session(rows)

    @asynccontextmanager
    async def __call__(self):
        yield self.session


@pytest.mark.anyio
async def test_user_repository_never_returns_password() -> None:
    repository = MySqlUserRepository(
        cast(
            Any,
            Factory(
            [
                {
                    "id": 1,
                    "username": "u",
                    "real_name": "U",
                    "phone": "13800000000",
                    "mail": "u@x.test",
                }
            ]
            ),
        )
    )
    user = await repository.get_by_username("u")
    assert user == {
        "id": 1,
        "username": "u",
        "realName": "U",
        "phone": "13800000000",
        "mail": "u@x.test",
    }
