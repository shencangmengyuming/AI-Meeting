import pytest
from sqlalchemy import text
from testcontainers.community.mysql import MySqlContainer

from app.infrastructure.mysql import create_mysql_resources, session_scope


@pytest.mark.integration
@pytest.mark.anyio
async def test_mysql_session_scope_rolls_back_uncommitted_work() -> None:
    with MySqlContainer("mysql:8.4") as container:
        url = container.get_connection_url().replace("mysql://", "mysql+asyncmy://")
        engine, session_factory = create_mysql_resources(url)
        try:
            async with engine.begin() as connection:
                await connection.execute(
                    text("CREATE TABLE rollback_probe (value INT NOT NULL)")
                )

            with pytest.raises(RuntimeError):
                async with session_scope(session_factory) as session:
                    await session.execute(
                        text("INSERT INTO rollback_probe (value) VALUES (1)")
                    )
                    raise RuntimeError("force rollback")

            async with session_factory() as session:
                count = await session.scalar(
                    text("SELECT COUNT(*) FROM rollback_probe")
                )
            assert count == 0
        finally:
            await engine.dispose()
