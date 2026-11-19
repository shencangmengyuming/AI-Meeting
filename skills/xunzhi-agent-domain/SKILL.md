---
name: xunzhi-agent-domain
description: Use when implementing or reviewing Python general Agent sessions, messages, history, files, streaming responses, or business-scene bindings.
---

# Agent Domain

The domain includes ordinary AI conversations, MySQL AI/Agent configuration,
OpenAI-compatible and Xunfei Providers, owned Agent sessions, streaming, file
assets and repair records.
Read `references/module-boundary.md` before extending general Agent behavior.
The current review and residual provider risks are recorded in
`docs/reviews/python-ai-agent-review.md`.

## Constraints

- Keep general Agent sessions separate from the interview workflow.
- Verify session ownership before history reads, writes, files, or streaming.
- Treat scene-to-Agent binding as runtime behavior, not display metadata.
- Keep provider SDK objects outside domain and application contracts.
- Define streaming cancellation, error, and completion behavior explicitly.

## Current Entry Points

- `app/agent/domain/configuration.py`
- `app/agent/domain/session.py`
- `app/agent/application/service.py`
- `app/agent/application/session.py`
- `app/agent/application/streaming.py`
- `app/agent/infrastructure/configuration.py`
- `app/agent/infrastructure/providers/xunfei.py`
- `app/agent/application/files.py`
- `app/agent/infrastructure/file_assets.py`
- `app/agent/api/router.py`
- `app/ai/application/conversations.py`
- `app/ai/application/chat.py`
- `app/ai/infrastructure/openai_compatible.py`
- `app/ai/api/router.py`
- `app/configuration/api/router.py`
- `tests/agent/`
