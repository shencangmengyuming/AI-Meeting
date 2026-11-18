# Runtime Reliability Contract

Runtime controls have separate responsibilities:

- Rate limit: cap admitted work by identity and operation.
- Guard: enforce timeout, concurrency, retry, and failure classification.
- Single-flight: coalesce equivalent in-flight calls and optionally reuse a
  short-lived result.
- Idempotency: prevent one business command from committing twice.

Do not use one mechanism as a substitute for another. A distributed
single-flight implementation needs stable keys, lock ownership tokens, bounded
follower waits, safe takeover, and token-checked release. A cached result is an
optimization unless the domain explicitly promotes it to durable truth.
