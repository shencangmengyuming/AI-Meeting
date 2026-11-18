import asyncio
from collections.abc import Awaitable
from typing import cast

import pytest
from redis.exceptions import ConnectionError
from sqlalchemy import text
from testcontainers.community.mysql import MySqlContainer
from testcontainers.core.container import DockerContainer

from app.auth_user.domain.session import AuthIdentity
from app.auth_user.infrastructure.user_identity import MySqlAuthIdentityLookup
from app.infrastructure.mysql import create_mysql_resources
from app.infrastructure.redis import create_redis_resource


@pytest.mark.integration
@pytest.mark.anyio
async def test_identity_lookup_reads_mysql_and_reuses_java_user_id_cache() -> None:
    with (
        MySqlContainer("mysql:8.4") as mysql,
        DockerContainer("redis:7").with_exposed_ports(6379) as redis_container,
    ):
        database_url = mysql.get_connection_url().replace(
            "mysql://", "mysql+asyncmy://"
        )
        engine, session_factory = create_mysql_resources(database_url)
        redis_url = (
            f"redis://{redis_container.get_container_host_ip()}:"
            f"{redis_container.get_exposed_port(6379)}/0"
        )
        redis = create_redis_resource(redis_url)
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
                        """
                        CREATE TABLE t_user (
                            id BIGINT PRIMARY KEY,
                            username VARCHAR(256) NOT NULL UNIQUE,
                            del_flag TINYINT NOT NULL
                        )
                        """
                    )
                )
                await connection.execute(
                    text(
                        """
                        CREATE TABLE admin_permission (
                            id BIGINT PRIMARY KEY AUTO_INCREMENT,
                            username VARCHAR(256) NOT NULL,
                            is_admin TINYINT NOT NULL,
                            del_flag TINYINT NOT NULL
                        )
                        """
                    )
                )
                await connection.execute(
                    text(
                        "INSERT INTO t_user (id, username, del_flag) "
                        "VALUES (101, 'alice', 0), (102, 'deleted', 1)"
                    )
                )
                await connection.execute(
                    text(
                        "INSERT INTO admin_permission "
                        "(username, is_admin, del_flag) VALUES ('alice', 1, 0)"
                    )
                )

            lookup = MySqlAuthIdentityLookup(session_factory, redis)

            assert await lookup.find_by_username("alice") == AuthIdentity(
                user_id=101,
                username="alice",
                roles=frozenset({"user", "admin"}),
            )
            assert await redis.get("xunzhi:user:id:alice") == b"101"
            assert await redis.ttl("xunzhi:user:id:alice") > 1790
            assert await lookup.find_by_username("deleted") is None

            async with engine.begin() as connection:
                await connection.execute(
                    text("DELETE FROM t_user WHERE username = 'alice'")
                )

            assert await lookup.find_by_username("alice") == AuthIdentity(
                user_id=101,
                username="alice",
                roles=frozenset({"user", "admin"}),
            )
        finally:
            await redis.aclose()
            await engine.dispose()
