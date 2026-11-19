# Python Interview Domain Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the independent Python AI interview domain with Session ownership, scoring, follow-up, idempotency, distributed coordination, recovery, reports and playback.

**Architecture:** Migrate read paths and Session lifecycle first. Build AI Guard, Single-flight and Runtime as independent deep modules before implementing the answer Pipeline. Redis remains online coordination/working state; Mongo Hot/Cold Snapshot and Turn Archive remain recovery truth; MySQL stores finalized reports.

**Tech Stack:** FastAPI, SQLAlchemy Async, PyMongo Async, redis-py asyncio/Lua, httpx, arq, Pydantic v2, pytest/AnyIO/Testcontainers.

**Spec:** `docs/superpowers/specs/2026-11-19-python-backend-rewrite-design.md`

**Historical baseline:** `docs/reference/java-backend-module-baseline.md`

## Global Constraints

- Every Session operation verifies `userId` ownership.
- Keep both form and JSON answer endpoints.
- Never award score before flow advancement and response assembly succeed.
- Follow-up rounds do not add the main-question score again.
- Old Single-flight Owners cannot write after takeover.
- Redis loss must be recoverable from Snapshot/Turn Archive.
- Finalized reports and replay history must be idempotent.

---

## Implementation Status

Status reconciled on 2026-11-19.

| Task | Status | Remaining work |
| --- | --- | --- |
| 1. Session Model and APIs | COMPLETE | Session ownership, lifecycle, paging and restore are implemented |
| 2. Question, Resume and Reports | COMPLETE | Question, resume, report, radar, playback and PDF paths are implemented |
| 3. AI Guard and Heavy Lock | COMPLETE | Timeout/retry/circuit, cancellation cleanup and Redis lock are implemented |
| 4. Distributed Single-Flight | COMPLETE | Lua arbitration, heartbeat, takeover, fencing and follower replay are implemented |
| 5. Runtime Snapshot and Rehydration | COMPLETE | Redis/Mongo restore, CAS verification and Turn Archive recovery are implemented |
| 6. State Machine and RuleChain | COMPLETE | State machine and configurable RuleChain are implemented and tested |
| 7. Extraction and Demeanor | COMPLETE | Upload, workflow parsing, persistence and score normalization exist |
| 8. Idempotency, Lock and Evaluation | COMPLETE | Replay repair, question locks and guarded evaluation are implemented |
| 9. Answer Pipeline and Turn Compensation | COMPLETE | Pipeline ordering, worker ownership and three-attempt repair are implemented |
| 10. Finalization and Reports | COMPLETE | Atomic finalization, playback, review feedback and report routes are implemented |

The status table is authoritative. Unchecked boxes below are retained as the
original task recipe and do not override the reconciled status.

### Task 1: Interview Session Model and Read APIs [COMPLETE]

**Files:**
- Create: `app/interview/domain/session.py`
- Create: `app/interview/infrastructure/sessions.py`
- Create: `app/interview/application/session_service.py`
- Create: `app/interview/api/router.py`
- Test: `tests/interview/test_session_service.py`
- Test: `tests/contracts/test_interview_session_reads.py`

**Interfaces:**
- Produces: `InterviewSessionRepository`
- Produces: create/page/finish/end/current read routes

- [ ] **Step 1: Write Session state and ownership tests**

Cover create, active-session abandonment, ready/in-progress/finished transitions, soft delete, paging filters, title search, cross-user access and `finish`/`end` alias behavior.

- [ ] **Step 2: Run tests**

Run: `python -m pytest tests/interview/test_session_service.py -v`

- [ ] **Step 3: Implement Session repository and routes**

Map the existing Mongo document fields and status strings exactly. Do not migrate answer writes yet.

- [ ] **Step 4: Run Python read contracts**

Run: `python -m pytest tests/contracts/test_interview_session_reads.py -v`

- [ ] **Step 5: Commit**

```bash
git add app/interview/domain app/interview/infrastructure/sessions.py app/interview/application app/interview/api/router.py tests
git commit -m "feat(python): migrate interview Session reads"
```

### Task 2: Question, Resume and Report Read Models [COMPLETE]

**Files:**
- Create: `app/interview/domain/questions.py`
- Create: `app/interview/domain/reports.py`
- Create: `app/interview/infrastructure/questions.py`
- Create: `app/interview/infrastructure/report_repository.py`
- Create: `app/interview/api/reports.py`
- Test: `tests/interview/test_report_reads.py`
- Test: `tests/contracts/test_resume_preview.py`

**Interfaces:**
- Produces questions/suggestions/score/resume score/radar/report/playback routes
- Produces PDF success and text/plain 400/502/500 error responses

- [ ] **Step 1: Write read fallback tests**

Cover Redis hit, Mongo/DB fallback, ownership, empty maps, score defaults, radar calculation, Turn playback ordering and report deserialization.

- [ ] **Step 2: Write resume preview response tests**

Assert content type, length, no-store headers, UTF-8 inline filename, and plain-text error status mapping.

- [ ] **Step 3: Implement read models and routes**

Keep the unusual `/interview/interview/...` report paths unchanged.

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/interview/test_report_reads.py tests/contracts/test_resume_preview.py -v`

- [ ] **Step 5: Commit**

```bash
git add app/interview/domain app/infrastructure app/interview/api/reports.py tests
git commit -m "feat(python): migrate interview read models"
```

### Task 3: AI Guard and Heavy Lock [COMPLETE]

**Files:**
- Create: `app/interview/application/ai_guard.py`
- Create: `app/interview/application/heavy_lock.py`
- Create: `app/core/concurrency.py`
- Test: `tests/interview/test_ai_guard.py`
- Test: `tests/integration/test_heavy_lock.py`

**Interfaces:**
- Produces: `AiCallGuard.execute(stage, operation)`
- Produces: `HeavyTaskLock.acquire(stage, session_id)` async context manager

- [ ] **Step 1: Write timeout/concurrency/circuit tests**

Cover per-stage timeout, max concurrency, retry counts, retryable classification, circuit open/half-open and cancellation cleanup.

- [ ] **Step 2: Write Heavy Lock tests**

Assert immediate failure for a duplicate heavy task and ownership-safe release.

- [ ] **Step 3: Implement guard and lock**

Start from the reviewed Java stage policies, then encode the accepted Python policies in settings and tests. Heavy Lock Key is `interview:ai:heavy:lock:{stage}:{sessionId}` and is separate from Single-flight.

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/interview/test_ai_guard.py tests/integration/test_heavy_lock.py -v`

- [ ] **Step 5: Commit**

```bash
git add app/interview/application/ai_guard.py app/interview/application/heavy_lock.py app/core/concurrency.py tests
git commit -m "feat(python): add interview AI guard and heavy lock"
```

### Task 4: Distributed Single-Flight [COMPLETE]

**Files:**
- Create: `app/ai_runtime/domain/singleflight/models.py`
- Create: `app/ai_runtime/application/singleflight/service.py`
- Create: `app/infrastructure/redis/lua/acquire_or_join.lua`
- Create: `app/infrastructure/redis/lua/flight_owner_writes.lua`
- Create: `app/infrastructure/redis/flight_repository.py`
- Create: `app/infrastructure/redis/flight_serializer.py`
- Test: `tests/singleflight/test_service.py`
- Test: `tests/integration/test_singleflight_takeover.py`

**Interfaces:**
- Produces: `DistributedSingleFlight.execute(stage, request_key, session_id, supplier)`
- Produces actions `OWNER_NEW`, `OWNER_TAKEOVER`, `FOLLOWER_WAIT`, `REPLAY_SUCCESS`, `REPLAY_FAILURE`

- [ ] **Step 1: Port serializer tests**

Cover plain/GZIP payloads, SHA-256 mismatch, unsupported schema, corrupt bytes and ownerToken metadata.

- [ ] **Step 2: Port Lua decision tests**

Cover missing state, active heartbeat, stale heartbeat, retryable/non-retryable failure, succeeded replay, cancelled/expired and follower count.

- [ ] **Step 3: Implement Fencing Token writes and heartbeat**

Every running/heartbeat/success/failure write validates ownerToken. Heartbeat task key is `requestKey|ownerToken`; old Owners receive a fencing error and cannot publish results.

- [ ] **Step 4: Run takeover and 100-way concurrency tests**

Run: `python -m pytest tests/singleflight tests/integration/test_singleflight_takeover.py -v`

- [ ] **Step 5: Commit**

```bash
git add app/ai_runtime/domain/singleflight app/ai_runtime/application/singleflight app/infrastructure/redis tests
git commit -m "feat(python): implement distributed Single-Flight"
```

### Task 5: Runtime Hot/Cold Snapshot and Rehydration [COMPLETE]

**Files:**
- Create: `app/interview/domain/runtime.py`
- Create: `app/interview/application/runtime_rehydrate.py`
- Create: `app/interview/application/runtime_snapshot.py`
- Create: `app/interview/application/hot_refresh.py`
- Create: `app/interview/infrastructure/runtime.py`
- Create: `app/infrastructure/redis/interview_runtime.py`
- Test: `tests/interview/test_runtime_rehydrate.py`
- Test: `tests/integration/test_runtime_cas.py`

**Interfaces:**
- Produces: `ensure_runtime(session_id, load_mode, scope) -> RuntimeView`
- Produces: `refresh_snapshot(trigger, mutation_id, turn)`

- [ ] **Step 1: Write scope/confidence tests**

Cover all load modes, scopes and confidence values; Redis-ready, partial Redis, Snapshot restore, Turn Archive restore, read-only degradation and terminal state.

- [ ] **Step 2: Write concurrent recovery and CAS tests**

Assert one recovery Owner, waiters recheck state, snapshot versions increase monotonically and duplicate mutation IDs do not reapply.

- [ ] **Step 3: Implement four-layer Runtime**

Use Redis for hot work, Mongo Hot Snapshot for checkpoints, Cold Snapshot for materials and Turn Archive for committed history. Hot refresh merges events by Session and supports force flush for finalization.

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/interview/test_runtime_rehydrate.py tests/integration/test_runtime_cas.py -v`

- [ ] **Step 5: Commit**

```bash
git add app/interview/domain/runtime.py app/interview/application app/interview/infrastructure/runtime.py app/infrastructure/redis/interview_runtime.py tests
git commit -m "feat(python): implement interview Runtime recovery"
```

### Task 6: Flow State Machine and Follow-Up Rule Chain [PARTIAL]

**Files:**
- Modify: `app/interview/domain/flow.py`
- Modify: `app/interview/domain/follow_up.py`
- Create: `app/interview/application/followup_rules.py`
- Create: `app/interview/config/followup_rules.yaml`
- Test: `tests/interview/test_flow_state_machine.py`
- Test: `tests/interview/test_followup_rules.py`

**Interfaces:**
- Produces: `InterviewFlowStateMachine`
- Produces: `FollowUpRuleChain.decide(context) -> FollowUpDecision`

- [ ] **Step 1: Write legal/illegal transition tests**

Cover INIT, ASKING, EVALUATING, FOLLOW_UP, COMPLETED, current index, question number, follow-up count, max follow-up and version CAS.

- [ ] **Step 2: Write ordered rule tests**

Cover completed guard, limit guard, AI suggestion, low score, missing points, final reason and fail-open behavior.

- [ ] **Step 3: Implement state and rule modules**

Keep state transition validation separate from rule decision. Rule node order comes from configuration but node implementations are registered explicitly.

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/interview/test_flow_state_machine.py tests/interview/test_followup_rules.py -v`

- [ ] **Step 5: Commit**

```bash
git add app/interview/domain app/interview/application app/interview/config tests/interview
git commit -m "feat(python): add interview flow and follow-up rules"
```

### Task 7: Question Extraction and Demeanor Vertical Slice [COMPLETE]

**Files:**
- Create: `app/interview/application/extraction.py`
- Create: `app/interview/application/demeanor.py`
- Create: `app/interview/application/response_parser.py`
- Modify: `app/interview/api/router.py`
- Test: `tests/interview/test_extraction.py`
- Test: `tests/interview/test_demeanor.py`
- Test: `tests/contracts/test_interview_heavy_contract.py`

**Interfaces:**
- Produces resume extraction and demeanor endpoints
- Consumes Heavy Lock, AI Guard, Single-flight, Provider and Runtime Snapshot

- [ ] **Step 1: Port parser and normalization tests**

Cover fenced JSON, alternate field shapes, missing content, invalid score ranges and Provider error mapping.

- [ ] **Step 2: Write full vertical-slice tests**

Assert one Owner under duplicate requests, replay result, file upload failure, Session status transitions and snapshot refresh.

- [ ] **Step 3: Implement extraction and demeanor services**

Do not let Router call Provider directly. Persist uploaded resume/photo metadata and classify failures before updating Session state.

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/interview/test_extraction.py tests/interview/test_demeanor.py tests/contracts/test_interview_heavy_contract.py -v`

- [ ] **Step 5: Commit**

```bash
git add app/interview/application app/interview/api/router.py tests
git commit -m "feat(python): migrate interview heavy workflows"
```

### Task 8: Answer Idempotency, Question Lock and Evaluation [COMPLETE]

**Files:**
- Create: `app/interview/application/answer_idempotency.py`
- Create: `app/interview/application/question_lock.py`
- Create: `app/interview/application/evaluation.py`
- Test: `tests/interview/test_answer_idempotency.py`
- Test: `tests/integration/test_question_lock.py`

**Interfaces:**
- Produces: `try_start -> REPLAY_EXISTS | PROCESSING | NEW`
- Produces: question-level lock async context manager
- Produces: normalized evaluation result

- [ ] **Step 1: Write idempotency tests**

Cover replay, processing, NEW with Snapshot/Archive fallback, replay-key repair, processing expiry and unknown external-result handling.

- [ ] **Step 2: Write lock/stale-question tests**

Check question number before and after lock; concurrent same-question submissions allow one commit.

- [ ] **Step 3: Implement evaluation through Single-flight and AI Guard**

Define and test the Python v1 request-key format. Do not commit score in this task.

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/interview/test_answer_idempotency.py tests/integration/test_question_lock.py -v`

- [ ] **Step 5: Commit**

```bash
git add app/interview/application tests
git commit -m "feat(python): add answer execution guards"
```

### Task 9: Answer Pipeline and Turn Compensation [COMPLETE]

**Files:**
- Create: `app/interview/application/answer_pipeline.py`
- Create: `app/interview/application/followup.py`
- Create: `app/interview/application/turn_repair.py`
- Create: `app/workers/repair_interview_turn.py`
- Modify: `app/interview/api/router.py`
- Test: `tests/interview/test_answer_pipeline.py`
- Test: `tests/integration/test_answer_concurrency.py`

**Interfaces:**
- Produces both answer endpoints and current/next question responses
- Produces idempotent Turn repair jobs

- [ ] **Step 1: Write branch-complete Pipeline tests**

Cover completed, out-of-range, main answer without follow-up, main answer with follow-up, follow-up answer, Agent failure fallback, score failure rollback and final question completion.

- [ ] **Step 2: Write concurrency and replay tests**

Run duplicate requestId, different requestIds for same question, lock timeout, replay after Redis loss and Turn append failure.

- [ ] **Step 3: Implement Pipeline ordering**

Use the exact sequence: validate, normalize requestId, idempotency, load current question, lock, revalidate, evaluate, rule decision, follow-up/advance, score commit, Turn, replay success, Runtime checkpoint.

- [ ] **Step 4: Implement arq compensation**

Repair only Turn/Snapshot. Use `message_id`, `mutation_id`, `session_id`, `request_id`, `seq`, `retry_count`; retry three times, then persist failure and alert.

- [ ] **Step 5: Run tests and commit**

Run: `python -m pytest tests/interview/test_answer_pipeline.py tests/integration/test_answer_concurrency.py -v`

```bash
git add app/interview/application app/workers/repair_interview_turn.py app/interview/api/router.py tests
git commit -m "feat(python): migrate interview answer Pipeline"
```

### Task 10: Finalization, Reports and Review Gate [COMPLETE]

**Files:**
- Create: `app/interview/application/finalize.py`
- Modify: `app/interview/api/reports.py`
- Create: `tests/contracts/test_interview_contract.py`
- Create: `docs/reviews/python-interview-review.md`
- Modify: `skills/xunzhi-interview-domain/SKILL.md`
- Modify: `skills/xunzhi-ai-runtime/SKILL.md`

**Interfaces:**
- Produces idempotent final report, playback and final Session state

- [ ] **Step 1: Write finalization concurrency tests**

Assert two finish/save-from-redis requests create one report, preserve Turn order and produce the same radar/review payload.

- [ ] **Step 2: Run the full Python Interview contract suite**

Compare all interview endpoints, both answer transports, errors, PDF response, recovery, reports and intentional security behavior.

- [ ] **Step 3: Conduct concurrency/recovery review**

Review score exactly-once, Flow rollback, Fencing Token, CAS monotonicity, archive uniqueness, repair idempotency and cancellation cleanup.

- [ ] **Step 4: Enable capabilities in risk order**

Enable read APIs, Session writes, heavy workflows, then answer Pipeline. Maintain Python feature switches and a previous-release rollback procedure.

- [ ] **Step 5: Update interview/runtime Skills and validate anchors**

Document Python paths, Flow, RuleChain, Runtime, Single-flight, compensation and report behavior, then run the Skill anchor validator.

- [ ] **Step 6: Commit**

```bash
git add app/interview tests docs/reviews/python-interview-review.md skills/xunzhi-interview-domain skills/xunzhi-ai-runtime
git commit -m "test(python): certify interview migration"
```
