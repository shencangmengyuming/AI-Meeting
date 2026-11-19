from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


class MySqlUserRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.session_factory = session_factory

    async def get_by_username(self, username: str) -> dict[str, Any] | None:
        async with self.session_factory() as session:
            result = await session.execute(
                text(
                    "SELECT id, username, real_name, phone, mail FROM t_user "
                    "WHERE username=:username AND del_flag=0 LIMIT 1"
                ),
                {"username": username},
            )
            row = result.mappings().first()
        return _user(row) if row else None

    async def update_self(self, username: str, values: dict[str, Any]) -> None:
        allowed = {k: values.get(k) for k in ("real_name", "phone", "mail")}
        async with self.session_factory() as session:
            await session.execute(
                text(
                    "UPDATE t_user SET real_name=:real_name, phone=:phone, "
                    "mail=:mail WHERE username=:username AND del_flag=0"
                ),
                {"username": username, **allowed},
            )
            await session.commit()

    async def page_users(self, offset: int, limit: int) -> list[dict[str, Any]]:
        async with self.session_factory() as session:
            result = await session.execute(
                text(
                    "SELECT id, username, real_name, phone, mail FROM t_user "
                    "WHERE del_flag=0 ORDER BY id DESC LIMIT :limit OFFSET :offset"
                ),
                {"limit": limit, "offset": offset},
            )
            rows = result.mappings().all()
        return [_user(row) for row in rows]

    async def grant_admin(self, username: str) -> None:
        async with self.session_factory() as session:
            await session.execute(
                text(
                    "INSERT INTO admin_permission(username,is_admin,del_flag) "
                    "VALUES(:username,1,0) ON DUPLICATE KEY UPDATE "
                    "is_admin=1,del_flag=0"
                ),
                {"username": username},
            )
            await session.commit()


def _user(row: Any) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "username": str(row["username"]),
        "realName": row.get("real_name"),
        "phone": row.get("phone"),
        "mail": row.get("mail"),
    }
