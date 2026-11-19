from collections.abc import Callable
from typing import Any, cast
from uuid import uuid4

from redis.asyncio import Redis
from redis.exceptions import ResponseError
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.errors import BusinessError

USERNAME_BLOOM_KEY = "ai-meeting:auth:registered-usernames"
LOCK_PREFIX = "ai-meeting:auth:lock:register:"
RELEASE_LOCK_SCRIPT = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('DEL', KEYS[1])
end
return 0
"""


class UserRegistrationService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        redis: Redis,
        *,
        token_factory: Callable[[], str] | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.redis = redis
        self.token_factory = token_factory or (lambda: str(uuid4()))

    async def has_username(self, username: str) -> bool:
        if not username:
            return False
        try:
            exists = await cast(
                Any,
                self.redis.execute_command(
                    "BF.EXISTS", USERNAME_BLOOM_KEY, username
                ),
            )
            if bool(exists):
                return False
        except (ResponseError, RuntimeError):
            pass
        return not await self._database_has_username(username)

    async def register(
        self,
        *,
        username: str,
        password: str,
        real_name: str | None = None,
        phone: str | None = None,
        mail: str | None = None,
    ) -> None:
        if not username or not password:
            raise BusinessError("A000001", "用户名和密码不能为空")
        if not await self.has_username(username):
            raise BusinessError("A000003", "用户名已存在")

        lock_key = LOCK_PREFIX + username
        lock_token = self.token_factory()
        acquired = await self.redis.set(lock_key, lock_token, nx=True, ex=10)
        if not acquired:
            raise BusinessError("A000003", "用户名已存在")
        try:
            try:
                async with self.session_factory() as session:
                    await session.execute(
                        text(
                            "INSERT INTO t_user "
                            "(username, password, real_name, phone, mail, del_flag) "
                            "VALUES (:username, :password, :real_name, "
                            ":phone, :mail, 0)"
                        ),
                        {
                            "username": username,
                            "password": password,
                            "real_name": real_name,
                            "phone": phone,
                            "mail": mail,
                        },
                    )
                    await session.commit()
            except IntegrityError as exc:
                raise BusinessError("A000003", "用户名已存在") from exc
            try:
                await cast(
                    Any,
                    self.redis.execute_command(
                        "BF.ADD", USERNAME_BLOOM_KEY, username
                    ),
                )
            except (ResponseError, RuntimeError):
                pass
        finally:
            await cast(
                Any,
                self.redis.eval(RELEASE_LOCK_SCRIPT, 1, lock_key, lock_token),
            )

    async def _database_has_username(self, username: str) -> bool:
        async with self.session_factory() as session:
            result = await session.scalar(
                text(
                    "SELECT EXISTS(SELECT 1 FROM t_user "
                    "WHERE username = :username AND del_flag = 0)"
                ),
                {"username": username},
            )
        return bool(result)
