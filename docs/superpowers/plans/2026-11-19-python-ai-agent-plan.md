# Python AI and Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement Python-owned AI/Agent configuration, Provider calls, conversations, message persistence, streaming protocols and Agent file assets without changing required frontend contracts.

**Architecture:** AI and Agent share a deep `conversation_streaming` module for history, sequence allocation, persistence and completion, but retain separate Provider adapters and separate SSE encoders. Configuration is loaded through repositories and versioned caches; business code resolves Agent by `BusinessAgentScene`.

**Tech Stack:** FastAPI, httpx AsyncClient, SQLAlchemy Async, PyMongo Async, Redis, Pydantic v2, pytest/AnyIO.

**Spec:** `docs/superpowers/specs/2026-11-19-python-backend-rewrite-design.md`

**Historical baseline:** `docs/reference/java-backend-module-baseline.md`

## Global Constraints

- Keep ordinary AI SSE and Agent SSE as distinct wire protocols.
- Every conversation and message read/write verifies ownership.
- Configuration and secret-bearing endpoints require admin.
- Never return raw `apiSecret`; mask API keys in read responses.
- Provider clients use bounded timeouts and are lifecycle-managed.
- Message sequence allocation is atomic per session.

---

## Implementation Status

Status reconciled on 2026-11-19. The interview module contains narrow Xunfei
scoring and follow-up adapters; those do not complete this shared AI/Agent batch.

| Task | Status |
| --- | --- |
| 1. AI and Agent Configuration Repositories | COMPLETE |
| 2. Business Agent Resolution and Cache Invalidation | COMPLETE |
| 3. Provider Interfaces and Adapters | COMPLETE |
| 4. Shared Conversation Persistence | COMPLETE |
| 5. Ordinary AI Conversations and SSE | COMPLETE |
| 6. Agent Conversations and SSE | COMPLETE |
| 7. Agent File Upload and Compensation | COMPLETE |
| 8. AI/Agent Review Gate | COMPLETE |

The status table is authoritative. All tasks in this plan remain open.

### Task 1: AI and Agent Configuration Repositories [COMPLETE]

**Files:**
- Create: `app/ai_agent/domain/ai/configuration.py`
- Create: `app/ai_agent/domain/agent/configuration.py`
- Create: `app/ai_agent/infrastructure/ai_config_repository.py`
- Create: `app/ai_agent/infrastructure/agent_config_repository.py`
- Create: `app/ai_agent/api/ai_properties.py`
- Create: `app/ai_agent/api/agent_properties.py`
- Test: `tests/configuration/test_ai_properties.py`
- Test: `tests/configuration/test_agent_properties.py`
- Test: `tests/contracts/test_configuration_contract.py`

**Interfaces:**
- Produces: `AiConfigRepository` and `AgentConfigRepository`
- Produces: all `/ai-properties` and `/agent-properties` routes

- [ ] **Step 1: Write schema and authorization tests**

Cover soft delete, enabled filtering, duplicate names, pagination, tag replacement, API key masking, secret omission and admin-only writes/reads.

- [ ] **Step 2: Run tests**

Run: `python -m pytest tests/configuration -v`

- [ ] **Step 3: Implement repositories and routes**

Map existing MySQL tables. Preserve Page/IPage response shapes. Treat the Java raw Agent secret response as a reviewed security delta: Python responses omit `apiSecret` and mask `apiKey`.

- [ ] **Step 4: Run tests and contract comparison**

Run: `python -m pytest tests/configuration tests/contracts/test_configuration_contract.py -v`

- [ ] **Step 5: Commit**

```bash
git add app/ai_agent tests/configuration tests/contracts
git commit -m "feat(python): migrate AI and Agent configuration"
```

### Task 2: Business Agent Resolution and Cache Invalidation [COMPLETE]

**Files:**
- Create: `app/ai_agent/domain/agent/scenes.py`
- Create: `app/ai_agent/application/agent_resolver.py`
- Create: `app/infrastructure/redis/config_events.py`
- Test: `tests/agent/test_agent_resolver.py`

**Interfaces:**
- Produces: `BusinessAgentResolver.resolve_required(scene) -> AgentConfig`
- Produces: `SessionAgentResolver.resolve(session_id, requested_agent_id) -> AgentConfig | None`

- [ ] **Step 1: Write resolver tests**

Cover configured name, alias fallback, missing Agent, Session binding overriding requested Agent, cache miss and stale-cache invalidation after update/delete.

- [ ] **Step 2: Run tests**

Run: `python -m pytest tests/agent/test_agent_resolver.py -v`

- [ ] **Step 3: Implement versioned cache**

Cache by Agent ID/name with a configuration version. Publish an invalidation event only after the MySQL transaction commits; subscribers remove matching entries. A cache miss always falls back to MySQL.

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/agent/test_agent_resolver.py -v`

- [ ] **Step 5: Commit**

```bash
git add app/ai_agent/domain/agent app/ai_agent/application/agent_resolver.py app/infrastructure/redis/config_events.py tests/agent
git commit -m "feat(python): add hot-reloadable Agent resolution"
```

### Task 3: Provider Interfaces and Adapters [COMPLETE]

**Files:**
- Create: `app/ai_agent/application/providers/chat.py`
- Create: `app/ai_agent/application/providers/workflow.py`
- Create: `app/ai_agent/infrastructure/providers/openai_compatible.py`
- Create: `app/ai_agent/infrastructure/providers/deepseek.py`
- Create: `app/ai_agent/infrastructure/providers/xunfei_agent.py`
- Test: `tests/providers/test_openai_compatible.py`
- Test: `tests/providers/test_xunfei_agent.py`

**Interfaces:**
- Produces: `ChatProvider.stream(messages, config) -> AsyncIterator[ChatChunk]`
- Produces: `AgentProvider.stream(request) -> AsyncIterator[bytes]`
- Produces: normalized `ProviderError(type, code, retryable)`

- [ ] **Step 1: Write mocked HTTP streaming tests**

Cover content chunks, reasoning chunks, malformed provider chunks, HTTP errors, timeout, cancellation and secret-free logging.

- [ ] **Step 2: Run tests**

Run: `python -m pytest tests/providers -v`

- [ ] **Step 3: Implement adapters**

Use the lifespan `httpx.AsyncClient`; do not instantiate clients per request. Keep provider-native payload parsing inside adapters.

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/providers -v`

- [ ] **Step 5: Commit**

```bash
git add app/ai_agent/application/providers app/ai_agent/infrastructure/providers tests/providers
git commit -m "feat(python): add chat and Agent provider adapters"
```

### Task 4: Shared Conversation Persistence [COMPLETE]

**Files:**
- Create: `app/ai_agent/domain/conversation/models.py`
- Create: `app/ai_agent/application/conversation_streaming.py`
- Create: `app/ai_agent/infrastructure/ai_conversations.py`
- Create: `app/ai_agent/infrastructure/agent_conversations.py`
- Create: `app/ai_agent/infrastructure/message_sequence.py`
- Test: `tests/conversation/test_streaming.py`
- Test: `tests/integration/test_message_sequence.py`

**Interfaces:**
- Produces: `ConversationStreamingService.execute(command) -> AsyncIterator[StreamChunk]`
- Produces: atomic `next_ai_seq(session_id)` and `next_agent_seq(session_id)`

- [ ] **Step 1: Write ordering and persistence tests**

Assert user message is persisted before Provider execution, assistant message after completion/error, sequence is monotonic under concurrency, and conversation counters update once.

- [ ] **Step 2: Run tests**

Run: `python -m pytest tests/conversation tests/integration/test_message_sequence.py -v`

- [ ] **Step 3: Implement the deep module**

Expose one execution interface while keeping AI/Agent persistence adapters separate. Cancellation must persist accumulated assistant content and an error marker according to the accepted Python contract.

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/conversation tests/integration/test_message_sequence.py -v`

- [ ] **Step 5: Commit**

```bash
git add app/ai_agent tests
git commit -m "feat(python): add conversation streaming core"
```

### Task 5: Ordinary AI Conversations and SSE [COMPLETE]

**Files:**
- Create: `app/ai_agent/api/ai_conversations.py`
- Create: `app/ai_agent/api/ai_messages.py`
- Create: `app/api/streaming/ai_sse.py`
- Test: `tests/api/test_ai_conversations.py`
- Test: `tests/contracts/test_ai_sse_contract.py`

**Interfaces:**
- Produces all `/ai/conversations` and `/ai/history` routes
- Produces `POST /ai/sessions/{sessionId}/chat`

- [ ] **Step 1: Record and write SSE golden tests**

Define golden Python headers/chunks for content, reasoning, completion, provider error and client cancellation. Historical Java frames may be consulted only to recover required frontend semantics.

- [ ] **Step 2: Write ownership and CRUD tests**

Cover create, page, update, end, soft delete, get, history and cross-user rejection.

- [ ] **Step 3: Implement routes and AI SSE encoder**

Emit the frontend-compatible JSON chunk shape without Agent's named `end` event. Preserve the accepted no-cache/keep-alive/CORS contract.

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/api/test_ai_conversations.py tests/contracts/test_ai_sse_contract.py -v`

- [ ] **Step 5: Commit**

```bash
git add app/ai_agent/api/ai_conversations.py app/ai_agent/api/ai_messages.py app/api/streaming tests
git commit -m "feat(python): migrate ordinary AI conversations"
```

### Task 6: Agent Conversations and SSE [COMPLETE]

**Files:**
- Create: `app/ai_agent/api/agent_conversations.py`
- Create: `app/api/streaming/agent_sse.py`
- Test: `tests/api/test_agent_conversations.py`
- Test: `tests/contracts/test_agent_sse_contract.py`

**Interfaces:**
- Produces all `/agents/sessions`, conversation, message history and end routes
- Produces Agent SSE with `event: end` and `data: [DONE]`

- [ ] **Step 1: Define Agent SSE golden fixtures**

Capture normal chunks, 18-second timeout behavior, Provider error and `[DONE]` completion.

- [ ] **Step 2: Write route and ownership tests**

Cover Session-bound Agent, history ordering, paging and cross-user rejection.

- [ ] **Step 3: Implement Agent routes and encoder**

Keep Provider bytes unmodified for data events and emit the named final event exactly once.

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/api/test_agent_conversations.py tests/contracts/test_agent_sse_contract.py -v`

- [ ] **Step 5: Commit**

```bash
git add app/ai_agent/api/agent_conversations.py app/api/streaming/agent_sse.py tests
git commit -m "feat(python): migrate Agent conversations"
```

### Task 7: Agent File Upload and Compensation [COMPLETE]

**Files:**
- Create: `app/ai_agent/domain/agent/file_assets.py`
- Create: `app/ai_agent/infrastructure/agent_file_repository.py`
- Create: `app/workers/repair_agent_file_asset.py`
- Create: `app/ai_agent/api/agent_files.py`
- Test: `tests/agent/test_file_upload.py`

**Interfaces:**
- Produces: `POST /api/xunzhi/v1/agents/files/upload`
- Produces: compensation job keyed by upload mutation ID

- [ ] **Step 1: Write upload tests**

Cover empty file, Session ownership, fallback business Agent, missing credentials, remote failure, DB failure after remote success, duplicate repair and response fields.

- [ ] **Step 2: Run tests**

Run: `python -m pytest tests/agent/test_file_upload.py -v`

- [ ] **Step 3: Implement upload and repair**

Validate Session ownership before resolving its Agent. When remote upload succeeds but DB persistence fails, enqueue an idempotent repair record containing the remote URL and metadata.

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/agent/test_file_upload.py -v`

- [ ] **Step 5: Commit**

```bash
git add app/ai_agent/domain/agent/file_assets.py app/ai_agent/infrastructure/agent_file_repository.py app/workers/repair_agent_file_asset.py app/ai_agent/api/agent_files.py tests/agent
git commit -m "feat(python): migrate Agent file assets safely"
```

### Task 8: AI/Agent Review Gate [COMPLETE]

**Files:**
- Create: `docs/reviews/python-ai-agent-review.md`
- Create: `tests/contracts/test_ai_agent_contract.py`
- Modify: `skills/xunzhi-agent-domain/SKILL.md`
- Modify: `skills/xunzhi-agent-domain/references/module-map.md`
- Modify: `skills/xunzhi-agent-domain/references/session-flow.md`

**Interfaces:**
- Produces: parity and intentional-security-delta report

- [ ] **Step 1: Run full module tests**

Run: `python -m pytest tests/configuration tests/providers tests/conversation tests/agent tests/api/test_ai_* tests/api/test_agent_* tests/contracts/test_ai* tests/contracts/test_agent* -v`

- [ ] **Step 2: Review secrets, ownership and stream cancellation**

Reject raw secret responses, missing ownership checks, unbounded history, leaked tasks or duplicate assistant messages.

- [ ] **Step 3: Enable reads, then writes, then SSE**

Enable configuration reads and conversation history first, CRUD second, and streaming endpoints last. Record latency, disconnect rate, Provider errors and persistence mismatches.

- [ ] **Step 4: Rehearse rollback with active streams**

Rollback deploys the previous Python release; existing streams finish or cancel cleanly without duplicate message persistence.

- [ ] **Step 5: Update Agent Skill and validate anchors**

Document Python Provider, conversation streaming, two SSE protocols, ownership and configuration invalidation, then run the Skill anchor validator.

- [ ] **Step 6: Commit**

```bash
git add docs/reviews/python-ai-agent-review.md tests skills/xunzhi-agent-domain
git commit -m "test(python): certify AI and Agent implementation"
```
