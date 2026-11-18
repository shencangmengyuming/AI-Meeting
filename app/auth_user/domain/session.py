from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class AuthIdentity:
    user_id: int
    username: str
    roles: frozenset[str] = frozenset()


@dataclass(frozen=True)
class AuthPrincipal:
    user_id: int
    username: str
    token: str
    roles: frozenset[str] = frozenset()


@dataclass(frozen=True)
class AuthToken:
    value: str
    expires_in: int


class AuthIdentityLookup(Protocol):
    async def find_by_username(self, username: str) -> AuthIdentity | None: ...


class AuthSessionPort(Protocol):
    async def resolve(self, token: str) -> AuthPrincipal | None: ...

    async def login(self, username: str) -> AuthToken: ...

    async def logout(self, token: str) -> None: ...
