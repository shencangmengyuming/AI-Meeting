---
name: xunzhi-ai-runtime
description: Use when implementing or reviewing Python AI provider execution, limits, retries, timeouts, guards, single-flight, task isolation, or shared runtime resources.
---

# AI Runtime

Read `references/resource-lifecycle.md` for current Foundation behavior and
`references/reliability-contract.md` before adding concurrency controls.
Interview heavy-workflow wiring and report finalization are reviewed in
`docs/reviews/python-interview-review.md`.

## Constraints

- Acquire shared clients from application lifespan resources.
- Keep business decisions out of provider adapters and runtime guards.
- Use stable operation keys for single-flight and idempotency.
- Bound retries by attempt count and deadline.
- Make cancellation and shutdown explicit for background tasks.
- Expose observable failure stages without leaking credentials or prompts.
