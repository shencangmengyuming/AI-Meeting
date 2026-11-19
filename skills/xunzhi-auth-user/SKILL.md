---
name: xunzhi-auth-user
description: Use when implementing or reviewing Python identity, login, current-user resolution, authorization, ownership checks, or WebSocket authentication.
---

# Auth And User Domain

Python-native Redis sessions, permission dependencies and the user management
surface are implemented. Read `references/session-contract.md` before changing
authentication or ownership behavior.
Registration Bloom rebuild and the registration race fallback are documented in
`docs/reviews/python-auth-user-review.md`.

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
- repo-path: `app/auth_user/infrastructure/redis_session.py`
- repo-path: `app/auth_user/infrastructure/user_identity.py`
- repo-path: `app/auth_user/infrastructure/user_repository.py`
- repo-path: `app/auth_user/api/user_router.py`
- repo-path: `tests/auth/test_redis_session_adapter.py`
- repo-path: `tests/auth/test_user_identity_lookup.py`
