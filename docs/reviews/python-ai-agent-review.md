# Python AI/Agent Review

Reviewed against the Java baseline and the Python implementation on 2026-11-19.

## Certified behavior

- Agent configuration is resolved from the configured repository and invalidated through Redis Pub/Sub.
- Agent sessions bind an Agent configuration server-side; client scene values cannot silently switch the bound Agent.
- Conversation history and message persistence are separated from interview records, with ownership checks on session, message and file paths.
- Ordinary AI SSE and Agent SSE remain distinct contracts; provider failures are encoded as structured stream errors.
- Failed file persistence is handed to a bounded repair worker with idempotent updates.

## Residual risks

- Concurrent cold configuration misses can call the repository more than once; this is a performance concern, not a correctness issue.
- Live provider credentials, quota behavior and cancellation under a real network disconnect require deployment drills.

## Gate result

Run the Agent/AI tests and stream cancellation checks before release; do not share interview and Agent persistence collections.
