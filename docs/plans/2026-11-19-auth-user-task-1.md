# Auth/User Task 1: Java Sa-Token Compatibility

## Goal

Accept Java-issued Sa-Token sessions and produce Python-issued sessions that
the Java service can read during dual-stack migration.

## Repository Paths

- Contract scenario: `tests/contracts/scenarios/auth.yaml`
- Captured contract: `tests/contracts/fixtures/auth/java_satoken.json`
- Contract test: `tests/contracts/test_java_satoken_fixture.py`
- Adapter tests: `tests/auth/test_java_satoken_adapter.py`
- Domain contract: `app/auth_user/domain/session.py`
- Redis adapter: `app/auth_user/infrastructure/java_satoken.py`
- Identity lookup: `app/auth_user/infrastructure/user_identity.py`

## Execution

1. Capture login, shared-token, check-login, TTL, Redis encoding, and logout
   behavior from the running Java baseline.
2. Store a normalized fixture with credentials and token values redacted.
3. Write failing tests for valid, expired, missing, shared, and logout cases.
4. Implement the minimum Redis adapter against the captured contract.
5. Resolve user IDs from `t_user` with the Java-compatible 30-minute Redis
   cache and derive the admin role from `admin_permission`.
6. Run focused tests, full quality gates, Skill validation, and update the Auth
   Skill with verified keys and ownership boundaries.

## Boundary

`Authorization:login:*` is the authentication truth. The legacy
`xunzhi-agent:login:*` hash is recorded for compatibility but remains outside
`AuthSessionPort`; user login/application services own it until the login route
is migrated.
