# Python Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Maintain the production-ready foundation of the independent FastAPI backend.

**Architecture:** `app/` is a modular monolith. FastAPI lifespan owns shared clients; routers only adapt transport; application modules depend on repository/provider interfaces; infrastructure adapters contain database and network details.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, pydantic-settings, SQLAlchemy 2.x Async, asyncmy, PyMongo Async, redis-py asyncio, httpx, structlog, OpenTelemetry/Prometheus, pytest, AnyIO, testcontainers.

**Spec:** `docs/superpowers/specs/2026-11-19-python-backend-rewrite-design.md`

## Global Constraints

- The repository root is the Python service root.
- Java is a business reference only; Foundation tests must not require Java.
- Use FastAPI lifespan for client creation and cleanup.
- Use an `AsyncSession` per request/task.
- Preserve Java `Result` field names and string error codes.
- Test against real MySQL, MongoDB and Redis containers for adapter behavior.
- No secrets or working credentials in committed configuration.

---

## Implementation Status

Status reconciled on 2026-11-19.

| Task | Status | Remaining work |
| --- | --- | --- |
| 1. Project Skeleton and Quality Gates | COMPLETE | Keep checks green |
| 2. Settings and Lifespan-Owned Clients | COMPLETE | Keep lifecycle tests green |
| 3. Result and Exception Layer | COMPLETE | Extend only for new product contracts |
| 4. Persistence Adapter Foundations | COMPLETE | Required async MySQL, Mongo, Redis and HTTP adapters are implemented |
| 5. Historical Contract Recorder | COMPLETE | Recorder, schemas and Python contract fixtures are present |
| 6. Container, CI and Review Gate | COMPLETE | Keep image and CI verification current |
| 7. Skill Anchor Validation | COMPLETE | Validator is scoped to this repository |

The status table is authoritative. Unchecked boxes below are retained as the
original task recipe and do not override the reconciled status.

### Task 1: Project Skeleton and Quality Gates [COMPLETE]

**Files:**
- Create: `pyproject.toml`
- Create: `app/__init__.py`
- Create: `app/main.py`
- Create: `app/api/router.py`
- Create: `tests/conftest.py`
- Create: `tests/test_health.py`
- Create: `README.md`

**Interfaces:**
- Produces: `create_app() -> FastAPI`
- Produces: `GET /actuator/health` compatible health endpoint

- [ ] **Step 1: Write the failing app and health tests**

```python
from httpx import ASGITransport, AsyncClient

from app.main import create_app


async def test_health_returns_up():
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/actuator/health")
    assert response.status_code == 200
    assert response.json()["status"] == "UP"
```

- [ ] **Step 2: Run the test and verify import failure**

Run: `python -m pip install -e '.[dev]' && python -m pytest tests/test_health.py -v`

Expected: FAIL because `app.main` does not exist.

- [ ] **Step 3: Add the project and minimal app**

Use a `src`-free package layout under `app`, configure Ruff and Pyright in `pyproject.toml`, and expose only `create_app()` at this stage.

- [ ] **Step 4: Run quality checks**

Run: `python -m ruff check . && python -m pyright && python -m pytest tests/test_health.py -v`

Expected: all commands exit 0.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml app tests README.md
git commit -m "feat(python): scaffold FastAPI backend"
```

### Task 2: Settings and Lifespan-Owned Clients [COMPLETE]

**Files:**
- Create: `app/core/settings.py`
- Create: `app/core/lifespan.py`
- Create: `app/infrastructure/mysql.py`
- Create: `app/infrastructure/mongodb.py`
- Create: `app/infrastructure/redis.py`
- Create: `app/infrastructure/http.py`
- Modify: `app/main.py`
- Test: `tests/core/test_lifespan.py`

**Interfaces:**
- Produces: `Settings` loaded from environment
- Produces: `AppResources(mysql_sessions, mongo, redis, http)`
- Produces: `get_resources(request: Request) -> AppResources`

- [ ] **Step 1: Write lifecycle tests with fake closable resources**

Assert startup creates each resource once and shutdown calls `engine.dispose()`, `mongo.close()`, `redis.aclose()` and `http.aclose()` exactly once.

- [ ] **Step 2: Run the lifecycle test**

Run: `python -m pytest tests/core/test_lifespan.py -v`

Expected: FAIL because lifespan resources are undefined.

- [ ] **Step 3: Implement settings and lifespan**

Use `@asynccontextmanager`. Configure SQLAlchemy with `mysql+asyncmy`, `async_sessionmaker(expire_on_commit=False)`, `AsyncMongoClient`, `redis.asyncio.Redis.from_url`, and one `httpx.AsyncClient` with explicit connect/read/write/pool timeouts.

- [ ] **Step 4: Verify lifecycle and static checks**

Run: `python -m pytest tests/core/test_lifespan.py -v && python -m ruff check app tests && python -m pyright`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/core app/infrastructure tests/core app/main.py
git commit -m "feat(python): add managed application resources"
```

### Task 3: Frontend-Compatible Result and Exception Layer [COMPLETE]

**Files:**
- Create: `app/core/result.py`
- Create: `app/core/errors.py`
- Create: `app/core/exception_handlers.py`
- Create: `app/core/request_id.py`
- Modify: `app/main.py`
- Test: `tests/core/test_result_contract.py`
- Test: `tests/core/test_validation_contract.py`

**Interfaces:**
- Produces: `Result[T](code: str, message: str | None, data: T | None, requestId: str | None)`
- Produces: `success(data=None)` and `failure(code, message)`
- Produces: `BusinessError(code, message, http_status=200)`

- [ ] **Step 1: Write golden serialization tests**

```python
def test_success_contract():
    assert success({"x": 1}).model_dump(by_alias=True) == {
        "code": "0", "message": None, "data": {"x": 1}, "requestId": None
    }
```

Also assert validation errors use Java's first-field-message behavior and malformed JSON returns code `A000001` with `请求体不能为空或格式错误`.

- [ ] **Step 2: Run tests and verify failure**

Run: `python -m pytest tests/core/test_result_contract.py tests/core/test_validation_contract.py -v`

- [ ] **Step 3: Implement aliases and exception handlers**

Return HTTP 200 for Java-style business errors unless an endpoint-specific contract requires 400/429/500/502. Keep `requestId=None` for compatibility while logging an internal trace ID separately.

- [ ] **Step 4: Run contract tests**

Run: `python -m pytest tests/core -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/core tests/core app/main.py
git commit -m "feat(python): reproduce Java response contracts"
```

### Task 4: Persistence Adapter Foundations [PARTIAL]

**Files:**
- Modify: `app/infrastructure/mysql.py`
- Modify: `app/infrastructure/mongodb.py`
- Modify: `app/infrastructure/redis.py`
- Create: `app/infrastructure/redis_scripts.py`
- Create: `tests/integration/test_mysql_resource.py`
- Create: `tests/integration/test_mongo_resource.py`
- Create: `tests/integration/test_redis_resource.py`

**Interfaces:**
- Produces: `session_scope() -> AsyncIterator[AsyncSession]`
- Produces: `MongoCollections` typed collection registry
- Produces: `LuaScriptRegistry.register(name, source)` and `execute(name, keys, args)`

- [ ] **Step 1: Write Testcontainers integration tests**

Test transaction rollback, Mongo insert/read/delete, Redis TTL, and a minimal Lua compare-and-set script.

- [ ] **Step 2: Run tests and confirm missing adapters**

Run: `python -m pytest tests/integration/test_*_resource.py -v`

- [ ] **Step 3: Implement the adapter foundations**

Do not create new production tables. Map existing schemas in later module plans. Ensure Redis scripts are loaded once and invoked by SHA with automatic reload after `NOSCRIPT`.

- [ ] **Step 4: Run integration tests**

Run: `python -m pytest tests/integration/test_*_resource.py -v`

Expected: PASS with containers.

- [ ] **Step 5: Commit**

```bash
git add app/infrastructure tests/integration
git commit -m "feat(python): add persistence adapter foundations"
```

### Task 5: Historical Java Contract Recorder [PARTIAL]

**Files:**
- Create: `tools/record_java_contracts.py`
- Create: `tests/contracts/fixtures/.gitkeep`
- Create: `tests/contracts/scenarios/foundation.yaml`
- Create: `tests/contracts/test_fixture_schema.py`
- Create: `tests/contracts/README.md`

**Interfaces:**
- Produces: versioned fixture JSON containing request, status, headers and raw response bytes
- Produces: SSE fixture format with timestamped raw chunks
- Produces: WebSocket fixture format with ordered inbound/outbound frames

- [ ] **Step 1: Write fixture schema tests**

Require `fixtureVersion`, `endpoint`, `request`, `response.status`, `response.headers`, and base64 `response.body`; streaming fixtures additionally require ordered frames.

- [ ] **Step 2: Run schema tests**

Run: `python -m pytest tests/contracts/test_fixture_schema.py -v`

- [ ] **Step 3: Implement the recorder**

The CLI accepts `--base-url`, `--token-env`, `--scenario-file`, and `--output`. It must redact Authorization, cookies, passwords, API keys, uploaded file contents and signed provider URLs before writing fixtures.

- [ ] **Step 4: Record foundation fixtures**

Run: `python tools/record_java_contracts.py --base-url "$JAVA_BASE_URL" --scenario-file tests/contracts/scenarios/foundation.yaml --output tests/contracts/fixtures/foundation`

Expected: fixtures for health, malformed JSON, validation failure, unauthenticated access and rate-limit response.

- [ ] **Step 5: Commit**

```bash
git add tools tests/contracts
git commit -m "test(python): add Java contract recorder"
```

### Task 6: Container, CI and Foundation Review Gate [COMPLETE]

**Files:**
- Create: `Dockerfile`
- Create: `.dockerignore`
- Create: `.github/workflows/python-backend.yml`
- Modify: `docker-compose.yml`
- Create: `docs/reviews/python-foundation-review.md`

**Interfaces:**
- Produces: Python service image with `/actuator/health`
- Produces: CI gates for Ruff, Pyright, unit and integration tests

- [ ] **Step 1: Add a container smoke test**

The test starts the image with dependency containers, waits for health, calls `/actuator/health`, then sends SIGTERM and asserts clean shutdown.

- [ ] **Step 2: Build and run smoke test**

Run: `docker compose build python-backend && docker compose run --rm python-backend-smoke`

Expected: health succeeds and shutdown exits 0.

- [ ] **Step 3: Add CI and review checklist**

The review document records dependency lifecycle, response compatibility, no committed secrets, session-per-task behavior and rollback instructions.

- [ ] **Step 4: Run the full foundation gate**

Run: `python -m ruff check . && python -m pyright && python -m pytest -v`

Expected: all checks pass.

- [ ] **Step 5: Commit**

```bash
git add Dockerfile .dockerignore .github/workflows/python-backend.yml docker-compose.yml docs/reviews/python-foundation-review.md
git commit -m "ci(python): enforce foundation quality gates"
```

### Task 7: Skill Anchor Validation [COMPLETE]

**Files:**
- Create: `tools/check_skill_anchors.py`
- Create: `tests/tools/test_check_skill_anchors.py`
- Modify: `skills/xunzhi-repo-map/SKILL.md`
- Modify: `skills/xunzhi-repo-map/references/module-routing.md`
- Modify: `skills/xunzhi-change-playbook/SKILL.md`
- Modify: `skills/xunzhi-change-playbook/references/cross-domain-checklist.md`
- Modify: `.github/workflows/python-backend.yml`

**Interfaces:**
- Produces: `check_skill_anchors.py --repo-root .` with nonzero exit on stale paths/routes/models

- [ ] **Step 1: Write validator tests**

Create temporary Skill references containing one valid Python path, one missing path and one stale route. Assert only the valid fixture passes.

- [ ] **Step 2: Run tests**

Run: `python -m pytest tests/tools/test_check_skill_anchors.py -v`

- [ ] **Step 3: Implement validator and update routing Skills**

The validator checks backticked repository paths, documented `/api/xunzhi/v1` routes and explicitly tagged Redis Keys. It reads only this repository and rejects external Java paths as Python implementation anchors.

- [ ] **Step 4: Add CI gate and run it**

Run: `python tools/check_skill_anchors.py --repo-root .`

Expected: exit 0 with counts for checked paths, routes and Redis Keys.

- [ ] **Step 5: Commit**

```bash
git add tools/check_skill_anchors.py tests/tools skills/xunzhi-repo-map skills/xunzhi-change-playbook .github/workflows/python-backend.yml
git commit -m "ci: validate Skill knowledge anchors"
```
