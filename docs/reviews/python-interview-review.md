# Python Interview Domain Review

Reviewed against the Java baseline and the Python implementation on 2026-11-19.

## Certified behavior

- Session ownership is checked on every read and write path.
- Answer requests support JSON and form transports, request-id replay, question locking, scoring, follow-up rules, flow advancement, turn archival and repair.
- Runtime recovery can use Redis, snapshots and archived turns; replay repairs the hot answer key from durable data.
- Heavy workflows use timeout/retry/circuit protection, distributed single-flight and a session/stage lock.
- Reports include ordered playback and structured review feedback; finalization uses an atomic Mongo upsert keyed by session/user/delFlag.

## Residual risks

- Startup creates unique indexes for report and turn identity; existing deployments should still verify index creation during rollout before enabling writes.
- Provider contract tests use fakes; live Xunfei credentials and network behavior remain deployment checks.
- Turn repair is intentionally limited to logs/snapshots and never reruns scoring.

## Gate result

Focused interview tests, Ruff and Pyright are required before release. The Skill anchor validator must pass after any path changes.
