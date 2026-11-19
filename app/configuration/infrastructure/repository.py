from typing import Any

from sqlalchemy import text


class MySqlConfigurationRepository:
    def __init__(
        self,
        session_factory: Any,
        *,
        table: str,
        columns: dict[str, str],
    ) -> None:
        if table not in {"ai_properties", "agent_properties"}:
            raise ValueError("unsupported configuration table")
        self.session_factory = session_factory
        self.table = table
        self.columns = columns

    async def get(self, item_id: int) -> dict[str, Any] | None:
        async with self.session_factory() as session:
            result = await session.execute(
                text(f"SELECT * FROM {self.table} WHERE id=:id AND del_flag=0"),
                {"id": item_id},
            )
            row = result.mappings().first()
        return self._map(row) if row else None

    async def page(self, offset: int, limit: int) -> list[dict[str, Any]]:
        async with self.session_factory() as session:
            result = await session.execute(
                text(
                    f"SELECT * FROM {self.table} WHERE del_flag=0 "
                    "ORDER BY id DESC LIMIT :limit OFFSET :offset"
                ),
                {"limit": limit, "offset": offset},
            )
            rows = result.mappings().all()
        return [self._map(row) for row in rows]

    async def create(self, values: dict[str, Any]) -> int:
        database_values = self._database_values(values)
        names = list(database_values)
        columns = ",".join(names) + ",del_flag"
        parameters = ",".join(f":{name}" for name in names) + ",0"
        async with self.session_factory() as session:
            result = await session.execute(
                text(f"INSERT INTO {self.table} ({columns}) VALUES ({parameters})"),
                database_values,
            )
            await session.commit()
            item_id = getattr(result, "lastrowid", None)
        if item_id is None:
            raise RuntimeError("configuration insert did not return an id")
        return int(item_id)

    async def update(self, values: dict[str, Any]) -> None:
        item_id = int(values["id"])
        database_values = self._database_values(values)
        assignments = ",".join(f"{name}=:{name}" for name in database_values)
        async with self.session_factory() as session:
            await session.execute(
                text(
                    f"UPDATE {self.table} SET {assignments} "
                    "WHERE id=:id AND del_flag=0"
                ),
                {"id": item_id, **database_values},
            )
            await session.commit()

    async def delete(self, item_id: int) -> None:
        async with self.session_factory() as session:
            await session.execute(
                text(f"UPDATE {self.table} SET del_flag=1 WHERE id=:id"),
                {"id": item_id},
            )
            await session.commit()

    async def find_by(self, public_name: str, value: Any) -> dict[str, Any] | None:
        database_name = self.columns.get(public_name)
        if database_name not in {"ai_name", "agent_name"}:
            raise ValueError("unsupported configuration lookup")
        async with self.session_factory() as session:
            result = await session.execute(
                text(
                    f"SELECT * FROM {self.table} WHERE {database_name}=:value "
                    "AND del_flag=0 LIMIT 1"
                ),
                {"value": value},
            )
            row = result.mappings().first()
        return self._map(row) if row else None

    async def enabled(self) -> list[dict[str, Any]]:
        condition = "AND is_enabled=1" if self.table == "ai_properties" else ""
        async with self.session_factory() as session:
            result = await session.execute(
                text(
                    f"SELECT * FROM {self.table} WHERE del_flag=0 {condition} "
                    "ORDER BY id DESC"
                )
            )
            rows = result.mappings().all()
        return [self._map(row) for row in rows]

    async def toggle(self, item_id: int, enabled: int) -> None:
        if self.table != "ai_properties":
            raise ValueError("status toggle is only supported for AI configuration")
        async with self.session_factory() as session:
            await session.execute(
                text(
                    "UPDATE ai_properties SET is_enabled=:enabled "
                    "WHERE id=:id AND del_flag=0"
                ),
                {"id": item_id, "enabled": 1 if enabled else 0},
            )
            await session.commit()

    def _map(self, row: Any) -> dict[str, Any]:
        return {
            public: row.get(database)
            for public, database in self.columns.items()
            if database in row
        }

    def _database_values(self, values: dict[str, Any]) -> dict[str, Any]:
        return {
            database: values[public]
            for public, database in self.columns.items()
            if public in values and public != "id"
        }
