---
name: xunzhi-auth-user
description: Use when implementing or reviewing Python identity, login, current-user resolution, authorization, ownership checks, or WebSocket authentication.
---

# Auth And User Domain

Sa-Token compatibility is implemented; user routes and permission dependencies
remain planned. Read `references/migration-contract.md` before extending it.

## Order

1. Define identity and ownership contracts.
2. Add contract tests for external behavior.
3. Implement transport-independent application services.
4. Bind HTTP and WebSocket authentication at their adapters.

## Constraints

- Use `user_id` for ownership; usernames are login/display identifiers.
- Authenticate before loading user-owned resources.
- Keep token parsing outside domain services.
- Enforce both token identity and path/session ownership for WebSockets.

## Current Entry Points

- repo-path: `app/auth_user/domain/session.py`
- repo-path: `app/auth_user/infrastructure/java_satoken.py`
- repo-path: `app/auth_user/infrastructure/user_identity.py`
- repo-path: `tests/contracts/fixtures/auth/java_satoken.json`
- repo-path: `tests/auth/test_java_satoken_adapter.py`
- repo-path: `tests/auth/test_user_identity_lookup.py`
