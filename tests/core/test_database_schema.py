import pytest

from app.infrastructure.schema import ensure_mysql_schema


class Connection:
    def __init__(self) -> None:
        self.statements: list[str] = []

    async def execute(self, statement) -> None:
        self.statements.append(str(statement))


class BeginContext:
    def __init__(self, connection: Connection) -> None:
        self.connection = connection

    async def __aenter__(self) -> Connection:
        return self.connection

    async def __aexit__(self, *args) -> None:
        return None


class Engine:
    def __init__(self) -> None:
        self.connection = Connection()

    def begin(self) -> BeginContext:
        return BeginContext(self.connection)


@pytest.mark.anyio
async def test_mysql_schema_contains_all_python_owned_tables() -> None:
    engine = Engine()

    await ensure_mysql_schema(engine)

    ddl = "\n".join(engine.connection.statements)
    for table in (
        "t_user",
        "admin_permission",
        "ai_properties",
        "agent_properties",
        "agent_file_asset",
    ):
        assert f"CREATE TABLE IF NOT EXISTS {table}" in ddl
    assert "UNIQUE KEY uq_t_user_username" in ddl
    assert "UNIQUE KEY uq_admin_permission_username" in ddl
