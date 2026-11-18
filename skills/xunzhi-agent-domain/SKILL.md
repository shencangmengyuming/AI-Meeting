---
name: xunzhi-agent-domain
description: Use when implementing or reviewing Python general Agent sessions, messages, history, files, streaming responses, or business-scene bindings.
---

# Agent Domain

This domain is not implemented yet. Read `references/module-boundary.md` before
adding general Agent behavior.

## Constraints

- Keep general Agent sessions separate from the interview workflow.
- Verify session ownership before history reads, writes, files, or streaming.
- Treat scene-to-Agent binding as runtime behavior, not display metadata.
- Keep provider SDK objects outside domain and application contracts.
- Define streaming cancellation, error, and completion behavior explicitly.
