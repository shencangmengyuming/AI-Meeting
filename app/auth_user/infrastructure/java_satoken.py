import json
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, cast
from uuid import uuid4

from redis.asyncio import Redis

from app.auth_user.domain.session import (
    AuthIdentityLookup,
    AuthPrincipal,
    AuthToken,
)

LOGIN_SCRIPT = """
local session_key = KEYS[1]
local token_prefix = ARGV[1]
local username = ARGV[2]
local candidate_token = ARGV[3]
local timeout_seconds = tonumber(ARGV[4])
local candidate_session = ARGV[5]

local session_json = redis.call('GET', session_key)
if session_json then
    local decoded, session = pcall(cjson.decode, session_json)
    if decoded and session['tokenSignList'] then
        local signs = session['tokenSignList'][2]
        local sign = signs and signs[1]
        local existing_token = sign and sign['value']
        if existing_token then
            local token_key = token_prefix .. existing_token
            if redis.call('GET', token_key) == username then
                redis.call('EXPIRE', token_key, timeout_seconds)
                redis.call('EXPIRE', session_key, timeout_seconds)
                return existing_token
            end
        end
    end
end

redis.call('SET', token_prefix .. candidate_token, username, 'EX', timeout_seconds)
redis.call('SET', session_key, candidate_session, 'EX', timeout_seconds)
return candidate_token
"""

LOGOUT_SCRIPT = """
local token_key = KEYS[1]
local session_prefix = ARGV[1]
local username = redis.call('GET', token_key)
if not username then
    return 0
end
redis.call('DEL', token_key)
redis.call('DEL', session_prefix .. username)
return 1
"""


@dataclass(frozen=True)
class SaTokenKeys:
    token_name: str = "Authorization"
    login_type: str = "login"

    def token(self, token: str) -> str:
        return f"{self.token_name}:{self.login_type}:token:{token}"

    def session(self, username: str) -> str:
        return f"{self.token_name}:{self.login_type}:session:{username}"

    @property
    def token_prefix(self) -> str:
        return f"{self.token_name}:{self.login_type}:token:"

    @property
    def session_prefix(self) -> str:
        return f"{self.token_name}:{self.login_type}:session:"


class JavaSaTokenAdapter:
    def __init__(
        self,
        redis: Redis,
        identity_lookup: AuthIdentityLookup,
        *,
        token_factory: Callable[[], str] | None = None,
        clock_ms: Callable[[], int] | None = None,
        timeout_seconds: int = 2_592_000,
    ) -> None:
        self.redis = redis
        self.identity_lookup = identity_lookup
        self.token_factory = token_factory or (lambda: str(uuid4()))
        self.clock_ms = clock_ms or (lambda: time.time_ns() // 1_000_000)
        self.timeout_seconds = timeout_seconds
        self.keys = SaTokenKeys()

    async def resolve(self, token: str) -> AuthPrincipal | None:
        if not token:
            return None
        username = _decode(await self.redis.get(self.keys.token(token)))
        if username is None:
            return None
        identity = await self.identity_lookup.find_by_username(username)
        if identity is None:
            return None
        return AuthPrincipal(
            user_id=identity.user_id,
            username=identity.username,
            token=token,
            roles=identity.roles,
        )

    async def login(self, username: str) -> AuthToken:
        if not username:
            raise ValueError("username cannot be empty")
        candidate_token = self.token_factory()
        session_json = self._session_json(username, candidate_token)
        result = await cast(
            Awaitable[Any],
            self.redis.eval(
                LOGIN_SCRIPT,
                1,
                self.keys.session(username),
                self.keys.token_prefix,
                username,
                candidate_token,
                self.timeout_seconds,
                session_json,
            ),
        )
        token = _decode(result)
        if token is None:
            raise RuntimeError("Sa-Token login script returned no token")
        return AuthToken(value=token, expires_in=self.timeout_seconds)

    async def logout(self, token: str) -> None:
        if not token:
            return
        await cast(
            Awaitable[Any],
            self.redis.eval(
                LOGOUT_SCRIPT,
                1,
                self.keys.token(token),
                self.keys.session_prefix,
            ),
        )

    def _session_json(self, username: str, token: str) -> str:
        session = {
            "@class": "cn.dev33.satoken.dao.SaSessionForJacksonCustomized",
            "id": self.keys.session(username),
            "type": "Account-Session",
            "loginType": self.keys.login_type,
            "loginId": username,
            "token": None,
            "createTime": self.clock_ms(),
            "dataMap": {
                "@class": "java.util.concurrent.ConcurrentHashMap",
            },
            "tokenSignList": [
                "java.util.Vector",
                [
                    {
                        "@class": "cn.dev33.satoken.session.TokenSign",
                        "value": token,
                        "device": "default-device",
                        "tag": None,
                    }
                ],
            ],
        }
        return json.dumps(session, ensure_ascii=False, separators=(",", ":"))


def _decode(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)
