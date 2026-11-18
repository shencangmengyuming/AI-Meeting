# Triage

1. Capture the failing request or event, expected outcome, actual outcome, and
   timestamps.
2. Check the health route and application startup/shutdown logs.
3. Locate the first boundary where expected state diverges: adapter,
   application flow, domain state, database, Redis, provider, or side effect.
4. Verify retries, duplicate delivery, cancellation, timeout, and lock ownership
   before assuming the core business rule is wrong.
5. Rebuild runtime state from its documented durable authority when testing
   recovery.
6. Turn the root cause into a focused test, then implement the fix.

Current diagnostic anchors:

- route: `GET /actuator/health`
- repo-path: `app/core/lifespan.py`
- repo-path: `app/core/exception_handlers.py`
- repo-path: `tests/integration`
