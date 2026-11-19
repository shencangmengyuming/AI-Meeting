# AI Meeting Backend Documentation

This directory is the documentation source of truth for the independent Python
backend. Documents under the Java repository are historical business references
only and must not be used as the active Python implementation plan.

## Decision Boundary

- `AI-Meeting-backend` is deployed and operated as an independent FastAPI
  backend.
- Java code is a reviewed source for business behavior, endpoint semantics and
  edge cases. It is not a runtime dependency.
- Python owns its authentication sessions, Redis keys, configuration, Skills,
  persistence adapters and deployment lifecycle.
- Java/Python shared tokens, shared Redis session serialization, gateway
  canaries and Java retirement are superseded migration decisions.
- Compatibility means preserving required frontend behavior where it remains a
  product requirement. It does not mean reproducing Java internals.

## Active Documents

- [Backend design](superpowers/specs/2026-11-19-python-backend-rewrite-design.md)
- [Implementation roadmap](superpowers/plans/2026-11-19-python-backend-rewrite-roadmap.md)
- [Foundation plan](superpowers/plans/2026-11-19-python-foundation-plan.md)
- [Auth/User plan](superpowers/plans/2026-11-19-python-auth-user-plan.md)
- [AI/Agent plan](superpowers/plans/2026-11-19-python-ai-agent-plan.md)
- [Interview plan](superpowers/plans/2026-11-19-python-interview-plan.md)
- [Media plan](superpowers/plans/2026-11-19-python-media-cutover-plan.md)

## Status Vocabulary

- `COMPLETE`: implemented and covered by the repository's current verification.
- `PARTIAL`: a usable slice exists, but the plan's full acceptance criteria are
  not met.
- `NOT STARTED`: no production implementation exists in this repository.
- `SUPERSEDED`: the task belongs to the abandoned Java/Python dual-stack plan
  and must not be implemented.

Status is evidence-based. A file existing is not enough to mark a task complete;
the corresponding behavior and tests must also exist.
