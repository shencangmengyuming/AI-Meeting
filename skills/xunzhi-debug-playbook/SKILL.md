---
name: xunzhi-debug-playbook
description: Use when diagnosing Python backend failures involving requests, resources, persistence, concurrency, recovery, AI calls, or media sessions.
---

# Debug Playbook

Start from evidence and the failing boundary. Read `references/triage.md`, then
switch to the owning domain Skill after isolating the layer.

## Constraints

- Reproduce before changing behavior.
- Correlate by request, session, user, operation, and attempt identifiers.
- Separate transport, application, domain, persistence, and provider failures.
- Treat cache loss as a recovery test, not proof that durable data is lost.
- Preserve logs needed for replay while redacting credentials and user data.
- Add a regression test that fails for the diagnosed cause.
