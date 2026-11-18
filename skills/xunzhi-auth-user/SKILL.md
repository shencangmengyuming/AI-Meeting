---
name: xunzhi-auth-user
description: Use when implementing or reviewing Python identity, login, current-user resolution, authorization, ownership checks, or WebSocket authentication.
---

# Auth And User Domain

This domain is not implemented yet. Read `references/migration-contract.md`
before creating its package or routes.

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
