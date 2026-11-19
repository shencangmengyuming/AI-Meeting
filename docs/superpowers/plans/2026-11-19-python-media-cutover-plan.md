# Python Media Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement long-text TTS, real-time ASR and WebSocket push in the independent Python backend.

**Architecture:** TTS and ASR are Provider adapters behind media application modules. Each WebSocket owns bounded queues and lifecycle Tasks. Cross-node push uses Redis routing so HTTP management requests can reach the instance that owns a connection. Deployment and rollback operate on Python releases rather than Java/Python route switching.

**Tech Stack:** FastAPI WebSocket, asyncio, httpx, redis-py asyncio Pub/Sub or Streams, Pydantic v2, pytest/AnyIO.

**Spec:** `docs/superpowers/specs/2026-11-19-python-backend-rewrite-design.md`

**Historical baseline:** `docs/reference/java-backend-module-baseline.md`

## Global Constraints

- Preserve WebSocket path, accepted Token parameter names, message types and stop/final distinction.
- Use bounded queues; never buffer unbounded audio.
- Cancel and await all sender/receiver/heartbeat Tasks on disconnect.
- Only supplier natural completion emits final; user stop does not fabricate final.
- TTS signed requests, status mapping and response fields remain compatible.
- Cross-node push must not depend on a process-local Session map.

---

## Implementation Status

Status reconciled on 2026-11-19.

| Task | Status |
| --- | --- |
| 1. Long-Text TTS Provider | COMPLETE |
| 2. AST Transcription Assembler | COMPLETE |
| 3. Xunfei ASR Provider | COMPLETE |
| 4. Audio WebSocket Endpoint | COMPLETE |
| 5. Cross-Node WebSocket Push | COMPLETE |
| 6. Media Load, Failure and Review Gate | COMPLETE |
| 7. Java Cutover and Retirement | SUPERSEDED |

The status table is authoritative. Tasks 1-6 are open; Task 7 must not be
executed.

### Task 1: Long-Text TTS Provider [COMPLETE]

**Files:**
- Create: `app/media/domain/tts.py`
- Create: `app/media/infrastructure/xunfei_tts.py`
- Create: `app/media/api/tts.py`
- Test: `tests/media/test_xunfei_tts.py`
- Test: `tests/contracts/test_tts_contract.py`

**Interfaces:**
- Produces: `create_task`, `query_task`, `synthesize_and_wait`
- Produces all three `/api/xunzhi/v1/xunfei/tts` routes

- [ ] **Step 1: Write signing and request tests**

Freeze time and assert HMAC-SHA256 signature input, Base64 authorization, GMT date, request path, text encoding and defaults.

- [ ] **Step 2: Write response and polling tests**

Cover status 5 success, 2/4 failure, timeout, invalid ranges, 100000-character limit, missing credentials and artifact downloads.

- [ ] **Step 3: Implement async Provider and routes**

Use `await asyncio.sleep`, never blocking sleep. Restrict artifact download hosts to the verified Xunfei host set and reject redirects to untrusted hosts.

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/media/test_xunfei_tts.py tests/contracts/test_tts_contract.py -v`

- [ ] **Step 5: Commit**

```bash
git add app/media/domain app/media/infrastructure/xunfei_tts.py app/media/api/tts.py tests/media tests/contracts
git commit -m "feat(python): migrate long-text TTS"
```

### Task 2: AST Transcription Assembler [COMPLETE]

**Files:**
- Create: `app/media/domain/transcription.py`
- Create: `app/media/application/ast_assembler.py`
- Test: `tests/media/test_ast_assembler.py`

**Interfaces:**
- Produces: `AstTranscriptionAssembler.apply(packet) -> RealtimeTranscriptionUpdate`
- Produces: `fullText`, `displayText`, `committedText`, `liveText`, `revision`, partial/final

- [ ] **Step 1: Recreate assembler behavior tests from the reviewed baseline**

Cover `pgs=apd`, `pgs=rpl`, unknown pgs, missing pgs, overlap reuse, sibling cleanup, punctuation-only updates, finalized monotonicity and final packet.

- [ ] **Step 2: Add sequence-based scenario tests**

Use the eight-packet no-pgs example and assert every intermediate TreeMap-equivalent state and displayed text.

- [ ] **Step 3: Implement assembler**

Keep the algorithm deterministic and side-effect free outside its Session state. `finalized` only upgrades with `old or new`.

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/media/test_ast_assembler.py -v`

- [ ] **Step 5: Commit**

```bash
git add app/media/domain app/media/application/ast_assembler.py tests/media/test_ast_assembler.py
git commit -m "feat(python): port AST transcription assembly"
```

### Task 3: Xunfei ASR Provider [COMPLETE]

**Files:**
- Create: `app/media/infrastructure/xunfei_asr.py`
- Create: `app/media/application/transcription_session.py`
- Test: `tests/media/test_xunfei_asr.py`

**Interfaces:**
- Produces: `XunfeiAsrProvider.run(audio_queue, update_sink, stop_event)`
- Produces: `TranscriptionSessionContext` with bounded audio queue and last update

- [ ] **Step 1: Write Provider protocol tests**

Cover signed URL, first/continue/last audio frames, receive parsing, heartbeat, supplier close, timeout and malformed packet.

- [ ] **Step 2: Write backpressure tests**

Fill the queue and assert the selected behavior is a bounded wait followed by a structured error, not memory growth or silent packet loss.

- [ ] **Step 3: Implement sender/receiver/heartbeat Tasks**

Use `asyncio.TaskGroup` or equivalent structured cancellation. Track last progress separately from heartbeat.

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/media/test_xunfei_asr.py -v`

- [ ] **Step 5: Commit**

```bash
git add app/media/infrastructure/xunfei_asr.py app/media/application/transcription_session.py tests/media/test_xunfei_asr.py
git commit -m "feat(python): add real-time ASR provider"
```

### Task 4: Audio WebSocket Endpoint [COMPLETE]

**Files:**
- Create: `app/media/api/websocket.py`
- Create: `app/media/application/connection_registry.py`
- Test: `tests/media/test_audio_websocket.py`
- Test: `tests/contracts/test_asr_websocket_contract.py`

**Interfaces:**
- Produces: `WS /api/xunzhi/v1/xunfei/audio-to-text/{userId}`
- Produces: connection registry keyed by user and connection ID

- [ ] **Step 1: Define WebSocket golden fixtures**

Capture accepted Token parameter aliases, unauthorized close behavior, open message, text control commands, binary chunks, heartbeat, stop, natural final, disconnect and error messages.

- [ ] **Step 2: Write endpoint lifecycle tests**

Assert path user matches Token user/ID, duplicate connections follow the accepted Python rule, stop closes audio input without fake final, and disconnect leaves zero Tasks/registry entries.

- [ ] **Step 3: Implement endpoint**

Use the ASR Provider and assembler through `TranscriptionSessionContext`. Do not place Provider logic in the route.

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/media/test_audio_websocket.py tests/contracts/test_asr_websocket_contract.py -v`

- [ ] **Step 5: Commit**

```bash
git add app/media/api/websocket.py app/media/application/connection_registry.py tests/media tests/contracts
git commit -m "feat(python): migrate audio transcription WebSocket"
```

### Task 5: Cross-Node WebSocket Push [COMPLETE]

**Files:**
- Create: `app/media/application/push_service.py`
- Create: `app/media/infrastructure/websocket_routing.py`
- Create: `app/media/api/management.py`
- Test: `tests/integration/test_cross_node_websocket_push.py`
- Test: `tests/contracts/test_websocket_management.py`

**Interfaces:**
- Produces online status and four push REST routes
- Produces: `WebSocketRouting.publish(user_id, envelope)`

- [ ] **Step 1: Write two-instance routing test**

Start two app instances sharing Redis, connect a user to instance A, call push REST on instance B, and assert the frame arrives once on A.

- [ ] **Step 2: Write management contract/security tests**

Preserve naked JSON response fields and English messages. Require admin for push routes; online status may remain authenticated read access.

- [ ] **Step 3: Implement routing**

Register connection ownership with node ID and TTL heartbeat. Publish targeted envelopes through Redis; the owning node writes to local WebSocket. Clean stale ownership on failed delivery.

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/integration/test_cross_node_websocket_push.py tests/contracts/test_websocket_management.py -v`

- [ ] **Step 5: Commit**

```bash
git add app/media/application/push_service.py app/media/infrastructure/websocket_routing.py app/media/api/management.py tests
git commit -m "feat(python): route WebSocket push across nodes"
```

### Task 6: Media Load, Failure and Review Gate [COMPLETE]

**Files:**
- Create: `tests/load/test_asr_connections.py`
- Create: `tests/load/test_tts_polling.py`
- Create: `docs/reviews/python-media-review.md`
- Modify: `skills/xunzhi-media-domain/SKILL.md`

**Interfaces:**
- Produces capacity and cleanup evidence

- [ ] **Step 1: Run ASR connection load**

Exercise expected concurrent WebSockets plus 25% headroom. Assert queue bounds, event-loop latency, memory plateau and zero leaked Tasks after disconnect.

- [ ] **Step 2: Run TTS polling load**

Verify outbound concurrency limits, timeout behavior and no blocking event-loop calls.

- [ ] **Step 3: Run provider/Redis failure drills**

Interrupt Xunfei, Redis and one Python node. Assert structured errors, connection cleanup and recovery of cross-node routing.

- [ ] **Step 4: Complete media Code Review**

Review authentication, backpressure, cancellation, final semantics, SSRF controls, secret logging and multi-instance behavior.

- [ ] **Step 5: Update media Skill and validate anchors**

Document Python ASR/TTS/WebSocket paths, queue backpressure, AST assembly and cross-node routing, then run the Skill anchor validator.

- [ ] **Step 6: Commit**

```bash
git add tests/load docs/reviews/python-media-review.md skills/xunzhi-media-domain
git commit -m "test(python): certify media migration"
```

### Task 7: Java Cutover and Retirement [SUPERSEDED]

This task is retained only to record the abandoned dual-stack plan. The Python
backend is independent; do not implement gateway route switching, shared-token
rollback or Java retirement from this repository.
