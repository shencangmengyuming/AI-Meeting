# Auth/User Task 1: Python-Native Sessions

## Goal

Implement the Python authentication/session boundary without depending on the
Java service or Java Sa-Token Redis serialization.

## Repository Paths

- Contract scenario: `tests/contracts/scenarios/auth.yaml`
- Adapter tests: `tests/auth/test_redis_session_adapter.py`
- Domain contract: `app/auth_user/domain/session.py`
- Redis adapter: `app/auth_user/infrastructure/redis_session.py`
- Identity lookup: `app/auth_user/infrastructure/user_identity.py`

## Execution

1. Define Python-owned token/session keys and expiration semantics.
2. Write contract tests for valid, expired, missing, shared, concurrent, and
   logout cases.
3. Implement atomic login/logout Redis scripts and token resolution.
4. Resolve user IDs from `t_user` with a 30-minute Redis accelerator and derive
   the admin role from `admin_permission`.
5. Run focused tests, full quality gates, Skill validation, and update the Auth
   Skill with verified keys and ownership boundaries.

## Boundary

`ai-meeting:auth:*` is the authentication truth. Legacy Java Sa-Token and
`xunzhi-agent:login:*` records are outside `AuthSessionPort` and are not read by
the Python backend.
