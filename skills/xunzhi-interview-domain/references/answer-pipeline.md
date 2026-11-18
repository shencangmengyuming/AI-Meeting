# Answer Pipeline

The Python answer use case should preserve this ordering:

1. Validate the command and normalize a stable `request_id`.
2. Return an existing idempotent result when present.
3. Load the current question and reject completed or mismatched state.
4. Acquire a question-scoped distributed lock.
5. Revalidate current state after lock acquisition.
6. Evaluate and normalize the scoring result.
7. Run follow-up rules, then ask the state machine to apply the legal outcome.
8. Commit score and flow changes with an explicit consistency boundary.
9. Assemble the response and append the turn log.
10. Persist a recoverable runtime checkpoint.

Do not model this as one HTTP handler. The API adapter should call one
application-level command handler or pipeline whose dependencies are explicit
and replaceable.
