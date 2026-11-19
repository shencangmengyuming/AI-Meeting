# Python Backend Implementation Roadmap

> **For agentic workers:** Use this roadmap to select the next incomplete batch,
> then execute the linked module plan. Verify status against code and tests before
> changing it.

**Goal:** Build an independent Python FastAPI modular monolith that reproduces
the required AI Meeting business behavior without a Java runtime dependency.

**Architecture:** The repository root is the Python service root. Feature code
lives under `app/<domain>/`; shared runtime infrastructure lives under
`app/core/` and `app/infrastructure/`. Java is a read-only business baseline,
not a co-running service, shared session provider or deployment target.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, SQLAlchemy Async, PyMongo
Async, redis-py asyncio, httpx, pytest, Ruff and Pyright.

**Spec:** `docs/superpowers/specs/2026-11-19-python-backend-rewrite-design.md`

## Global Constraints

- Resolve all paths relative to this repository root.
- Keep domain code inside its owning `app/<domain>/` package.
- Preserve required frontend HTTP/SSE/WebSocket contracts, while allowing
  reviewed security and internal-storage improvements.
- Python owns Token/session storage. Do not add Java Sa-Token readers or writers.
- Do not require Java startup, shared Java Redis serialization, gateway routing
  or Java/Python dual writes in tests or production code.
- Java behavior may be captured as a fixture only when it clarifies a business
  contract. New tests must run against the Python repository independently.
- Update the matching Python Skill after a domain behavior or boundary changes.
- Do not advance a batch with unresolved severity-1 or severity-2 findings.

## Current Status

Status last reconciled against the repository on 2026-11-19.

| Batch | Status | Current evidence | Next gate |
| --- | --- | --- | --- |
| Foundation | COMPLETE | FastAPI skeleton, lifespan resources, result/errors, persistence clients, Docker/CI and Skill validator exist | Keep quality gates green |
| Auth/User | COMPLETE | Python sessions, login/logout, registration, Bloom rebuild, permissions and all baseline user routes exist | Keep quality gates green |
| AI/Agent | COMPLETE | AI/Agent configs, invalidation, providers, SSE, owned conversations, files and repair worker exist | Keep quality gates green |
| Interview | COMPLETE | RuleChain, fenced Single-flight, CAS, extraction/demeanor, compensation, recovery, answer pipeline and atomic reports exist | Keep quality gates green |
| Media | COMPLETE | AST, TTS, ASR tasks, bounded queues, authenticated WebSocket and cross-node routing exist | Run deployment-sized load/failure drills |
| Java cutover | SUPERSEDED | Independent Python backend decision | No implementation work |

## Plan Set

1. `2026-11-19-python-foundation-plan.md`
2. `2026-11-19-python-auth-user-plan.md`
3. `2026-11-19-python-ai-agent-plan.md`
4. `2026-11-19-python-interview-plan.md`
5. `2026-11-19-python-media-cutover-plan.md`

## Batch Gates

| Gate | Evidence required |
| --- | --- |
| G0 Foundation | health, lifecycle cleanup, result/error tests, resource integration tests, Ruff, Pyright and Skill validation |
| G1 Auth/User | Python session lifecycle, login/logout, password upgrade, registration race, permissions and user-route tests |
| G2 AI/Agent | configuration resolution, provider errors, message persistence, SSE framing, ownership and file compensation tests |
| G3 Interview | idempotency, locks, RuleChain, Single-flight, Runtime recovery, scoring consistency, Turn compensation and report tests |
| G4 Media | TTS/ASR provider tests, AST assembly, queue backpressure, WebSocket cleanup and cross-node push tests |

## Review Protocol

```text
write or update a failing test
-> implement the smallest complete behavior
-> run focused tests
-> run module tests
-> run repository quality gates
-> review security/concurrency/storage/error behavior
-> update the matching Skill and plan status
-> commit
```

The Python implementation and its tests are the current truth. When Java and
Python differ, first determine whether the difference is a required product
contract, an intentional Python decision, or an implementation defect; do not
automatically restore Java internals.
