# Python Auth and User Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete Python-owned authentication, current-user resolution, permissions, user endpoints and registration protection.

**Architecture:** FastAPI dependencies consume a Python-owned `AuthSessionPort`. `RedisSessionAdapter` owns `ai-meeting:auth:*` session records and never reads Java Sa-Token keys. User persistence maps the existing MySQL schema; registration uses Bloom fast rejection, username locking and the database unique index.

**Tech Stack:** FastAPI dependencies, SQLAlchemy Async, redis-py asyncio, Argon2/pwdlib, Pydantic v2, pytest, Testcontainers.

**Spec:** `docs/superpowers/specs/2026-11-19-python-backend-rewrite-design.md`

**Historical baseline:** `docs/reference/java-backend-module-baseline.md`

## Global Constraints

- Preserve `Authorization: Bearer <uuid>` and 2592000-second session timeout.
- Python defines and tests its own concurrent-login/session behavior.
- Do not add Java Sa-Token readers, writers or shared-session fixtures.
- Existing plaintext/legacy password rows must continue to authenticate until upgraded.
- `has-username=true` means the username is available.
- Admin-only security deltas are intentional and must have explicit tests.

---

## Implementation Status

Status reconciled on 2026-11-19.

| Task | Status | Remaining work |
| --- | --- | --- |
| 1. Python-Native Session Contract | COMPLETE | Keep Redis scripts and TTL tests green |
| 2. Current User and Permissions | COMPLETE | Keep route authorization tests green |
| 3. User Models and Repository | COMPLETE | Keep profile, paging and update mappings aligned |
| 4. Registration Bloom and Concurrency | COMPLETE | Bloom rebuild, temporary-key swap and registration race coverage are implemented |
| 5. Login and User Routes | COMPLETE | All 11 baseline routes are present |
| 6. Auth/User Review Gate | COMPLETE | Review recorded in `docs/reviews/python-auth-user-review.md`; Python tests and anchor checks pass |

The status table is authoritative. Unchecked boxes below are retained as the
original task recipe and do not override the reconciled status.

### Task 1: Python-Native Session Contract [COMPLETE]

**Files:**
- Create: `tests/contracts/scenarios/auth.yaml`
- Create: `tests/auth/test_redis_session_adapter.py`
- Create: `app/auth_user/domain/session.py`
- Create: `app/auth_user/infrastructure/redis_session.py`
- Create: `app/auth_user/infrastructure/user_identity.py`

**Interfaces:**
- Produces: `AuthSessionPort.resolve(token: str) -> AuthPrincipal | None`
- Produces: `AuthSessionPort.login(username: str) -> AuthToken`
- Produces: `AuthSessionPort.logout(token: str) -> None`

- [x] **Step 1: Define Python session keys and lifecycle behavior**

Use the `ai-meeting:auth:*` namespace for token, user-token and identity cache records. Define TTL, concurrent login and logout behavior in Python tests.

- [x] **Step 2: Cover session behavior**

Test valid token, expired token, missing identity mapping, concurrent login and logout without starting Java.

- [x] **Step 3: Implement the Redis adapter**

Keep the key formatter and atomic login/logout scripts inside the adapter. `AuthPrincipal` contains `user_id`, `username`, `token`, and `roles`; user identity is resolved through MySQL with a bounded Redis cache.

- [x] **Step 4: Run tests**

Run: `python -m pytest tests/auth/test_redis_session_adapter.py tests/auth/test_user_identity_lookup.py -v`

- [ ] **Step 5: Commit**

```bash
git add app/auth_user/domain app/auth_user/infrastructure tests/auth
git commit -m "feat(auth): add Python-native sessions"
```

### Task 2: Current User and Permission Dependencies [PARTIAL]

**Files:**
- Create: `app/auth_user/domain/permissions.py`
- Modify: `app/auth_user/api/dependencies.py`
- Create: `tests/auth/test_dependencies.py`
- Create: `tests/auth/test_permissions.py`

**Interfaces:**
- Produces: `require_current_user() -> AuthPrincipal`
- Produces: `require_admin() -> AuthPrincipal`
- Produces: `require_self_or_admin(username: str) -> AuthPrincipal`

- [ ] **Step 1: Write dependency tests**

Cover missing Header, invalid Bearer token, valid user, admin role, non-admin rejection and self-or-admin access. Authentication transport is `Authorization: Bearer`; Query Token support requires a separate product decision.

- [ ] **Step 2: Run tests and verify failures**

Run: `python -m pytest tests/auth/test_dependencies.py tests/auth/test_permissions.py -v`

- [ ] **Step 3: Implement dependencies**

Map authentication failures to the Python error contract. Apply admin requirements to config management, user paging and server-side push in their respective module plans.

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/auth -v`

- [ ] **Step 5: Commit**

```bash
git add app/auth_user/domain/permissions.py app/auth_user/api/dependencies.py tests/auth
git commit -m "feat(python): add current-user permission dependencies"
```

### Task 3: User Models, Repository and DTO Compatibility [PARTIAL]

**Files:**
- Create: `app/auth_user/domain/models.py`
- Create: `app/auth_user/domain/repository.py`
- Create: `app/auth_user/infrastructure/user_repository.py`
- Create: `app/auth_user/api/schemas.py`
- Test: `tests/auth/test_user_repository.py`
- Test: `tests/auth/test_user_schemas.py`

**Interfaces:**
- Produces: `UserRepository.get_by_username`, `insert`, `update_self`, `page_users`
- Produces: request/response aliases matching Java DTO fields

- [ ] **Step 1: Write repository tests against the existing schema**

Cover soft deletion, username uniqueness, pagination order, keyword matching and phone masking differences between `UserRespDTO`, `UserActualRespDTO` and `UserPageRespDTO`.

- [ ] **Step 2: Run tests**

Run: `python -m pytest tests/auth/test_user_repository.py tests/auth/test_user_schemas.py -v`

- [ ] **Step 3: Implement models and adapter**

Map `t_user` and `admin_permission` without Alembic schema changes. Do not expose password. Preserve long integer IDs as JSON numbers.

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/auth -v`

- [ ] **Step 5: Commit**

```bash
git add app/auth_user/domain app/auth_user/infrastructure/user_repository.py app/auth_user/api/schemas.py tests/auth
git commit -m "feat(python): map existing user persistence"
```

### Task 4: Registration Bloom Filter and Concurrency [PARTIAL]

**Files:**
- Create: `app/auth_user/domain/registration.py`
- Create: `app/infrastructure/redis/bloom.py`
- Create: `app/infrastructure/redis/locks.py`
- Create: `app/workers/rebuild_user_bloom.py`
- Test: `tests/auth/test_registration.py`
- Test: `tests/integration/test_registration_race.py`

**Interfaces:**
- Produces: `UserRegistrationService.is_available(username) -> bool`
- Produces: `UserRegistrationService.register(command) -> None`
- Produces: `rebuild_user_bloom(batch_size: int) -> RebuildStats`

- [ ] **Step 1: Write Bloom and race tests**

Cover miss, true hit, false positive with DB fallback, Redis failure fallback, 20 concurrent same-name registrations, DB duplicate-key mapping and transaction rollback before Bloom write.

- [ ] **Step 2: Run tests and verify failures**

Run: `python -m pytest tests/auth/test_registration.py tests/integration/test_registration_race.py -v`

- [ ] **Step 3: Implement registration**

Use a versioned Python Bloom Key unless compatibility tests prove Redisson bit-layout parity. Acquire `LOCK_USER_REGISTER_KEY + username`, insert in a SQL transaction, commit, then add to Bloom. If Redis fails, rely on MySQL.

- [ ] **Step 4: Implement rebuild worker and verify**

Run: `python -m pytest tests/auth/test_registration.py tests/integration/test_registration_race.py -v`

- [ ] **Step 5: Commit**

```bash
git add app/auth_user/domain/registration.py app/infrastructure/redis app/workers/rebuild_user_bloom.py tests
git commit -m "feat(python): add safe user registration coordination"
```

### Task 5: Login, Password Upgrade and User Routes [PARTIAL]

**Files:**
- Create: `app/auth_user/domain/authentication.py`
- Create: `app/auth_user/api/user_router.py`
- Modify: `app/auth_user/api/router.py`
- Test: `tests/auth/test_user_routes.py`
- Test: `tests/auth/test_password_upgrade.py`

**Interfaces:**
- Produces all 11 `/api/xunzhi/v1/users` routes
- Produces legacy-password verification followed by Argon2 rehash after successful login

- [ ] **Step 1: Write route contract tests**

Cover login, check-login, logout, registration, username availability, current-user update and error bodies with Python API tests. User paging requires admin; `actual/{username}` requires self-or-admin.

- [ ] **Step 2: Write password migration tests**

Legacy row authenticates once, is replaced with Argon2 hash in the same transaction, and subsequent login uses Argon2. Wrong passwords never trigger rehash.

- [ ] **Step 3: Implement routes and authentication**

Return `token`, `username`, `isAdmin` exactly. Preserve UUID token style and the documented Python concurrent-login behavior. Do not expose whether a username exists through different timing in login.

- [ ] **Step 4: Run module and contract tests**

Run: `python -m pytest tests/auth tests/auth tests/auth/test_user_routes.py -v`

- [ ] **Step 5: Commit**

```bash
git add app/auth_user/domain app/auth_user/api/user_router.py app/auth_user/api/router.py tests
git commit -m "feat(python): migrate auth and user endpoints"
```

### Task 6: Auth/User Review Gate [COMPLETE]

**Files:**
- Create: `docs/reviews/python-auth-user-review.md`
- Create: `tests/contracts/test_users_contract.py`
- Modify: `skills/xunzhi-auth-user/SKILL.md`
- Modify: `skills/xunzhi-auth-user/references/login-and-permission.md`
- Modify: `skills/xunzhi-auth-user/references/current-user.md`

**Interfaces:**
- Produces: endpoint-by-endpoint contract report and Python rollback procedure

- [ ] **Step 1: Run the Python Auth/User contract suite**

Compare all 11 endpoints for authorized success, validation failure, unauthorized access and duplicate registration. Mark the intentional admin/self authorization deltas separately.

- [ ] **Step 2: Run security and concurrency review**

Review token leakage, password logs, user enumeration, lock ownership, unique index behavior, Bloom recovery and Redis failure.

- [ ] **Step 3: Enable routes in risk order**

Enable `check-login`, `is-admin` and self user reads first; compare error rate and latency before enabling login/register/update in the same Python service.

- [ ] **Step 4: Verify rollback**

Exercise rollback by restoring the previous Python application version and verify existing Python sessions follow the documented compatibility policy.

- [ ] **Step 5: Update Skill and run anchor validation**

Document Python auth adapters, security deltas, Bloom rebuild and Python Session behavior, then run: `python tools/check_skill_anchors.py --repo-root .`.

- [ ] **Step 6: Commit**

```bash
git add docs/reviews/python-auth-user-review.md tests skills/xunzhi-auth-user
git commit -m "test(python): certify auth and user migration"
```
