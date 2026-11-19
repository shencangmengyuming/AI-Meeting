import asyncio
from collections.abc import Awaitable
from typing import cast

import pytest
from redis.exceptions import ConnectionError
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from testcontainers.community.mysql import MySqlContainer
from testcontainers.core.container import DockerContainer

from app.auth_user.application.registration import UserRegistrationService
from app.core.errors import BusinessError
from app.infrastructure.mysql import create_mysql_resources
from app.infrastructure.redis import create_redis_resource


@pytest.mark.integration
@pytest.mark.anyio
async def test_concurrent_registration_has_one_winner() -> None:
    with (
        MySqlContainer("mysql:8.4") as mysql,
        DockerContainer("redis:7").with_exposed_ports(6379) as redis_container,
    ):
        database_url = mysql.get_connection_url().replace(
            "mysql://", "mysql+asyncmy://"
        )
        engine, session_factory = create_mysql_resources(database_url)
        redis = create_redis_resource(
            f"redis://{redis_container.get_container_host_ip()}:{redis_container.get_exposed_port(6379)}/0"
        )
        try:
            for _ in range(30):
                try:
                    await cast(Awaitable[bool], redis.ping())
                    break
                except ConnectionError:
                    await asyncio.sleep(0.2)
            else:
                pytest.fail("Redis container did not become ready")

            async with engine.begin() as connection:
                await connection.execute(
                    text(
                        "CREATE TABLE t_user ("
                        "id BIGINT AUTO_INCREMENT PRIMARY KEY, "
                        "username VARCHAR(256) NOT NULL UNIQUE, "
                        "password VARCHAR(512), real_name VARCHAR(256), "
                        "phone VARCHAR(128), mail VARCHAR(512), del_flag TINYINT)"
                    )
                )

            service = UserRegistrationService(session_factory, redis)

            async def attempt() -> str:
                try:
                    await service.register(username="race-user", password="secret")
                    return "won"
                except (BusinessError, IntegrityError):
                    return "lost"

            results = await asyncio.gather(attempt(), attempt())

            assert sorted(results) == ["lost", "won"]
            async with engine.connect() as connection:
                count = await connection.scalar(
                    text("SELECT COUNT(*) FROM t_user WHERE username = 'race-user'")
                )
            assert count == 1
        finally:
            await redis.aclose()
            await engine.dispose()
