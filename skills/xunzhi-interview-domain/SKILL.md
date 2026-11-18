---
name: xunzhi-interview-domain
description: Use when implementing or reviewing Python interview sessions, question generation, answer scoring, follow-up decisions, flow state, restoration, or finalization.
---

# Interview Domain

This domain is not implemented yet. Preserve the reviewed business behavior,
but design Python modules around Python boundaries.

## Order

1. Read `references/invariants.md`.
2. Read `references/answer-pipeline.md` for answer submission.
3. Add compatibility fixtures and failing tests.
4. Implement one vertical slice without bypassing the flow state.

## Constraints

- Keep session lifecycle and question-flow state distinct.
- Treat `request_id` as the answer idempotency boundary.
- Serialize concurrent submissions for the same question.
- Separate follow-up decision rules from legal state transitions.
- Recovery and finalization are first-class contracts.
