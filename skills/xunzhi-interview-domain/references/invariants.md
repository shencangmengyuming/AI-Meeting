# Interview Invariants

Planned package boundary: `app/interview/`.

Required invariants:

1. A session belongs to one user and every command verifies ownership.
2. An answer targets the currently active business question.
3. Replaying the same `request_id` returns the committed result without
   repeating scoring or flow advancement.
4. Concurrent answers for one active question cannot both advance the flow.
5. AI output is untrusted input and must be parsed, validated, and normalized.
6. The state machine decides whether a transition is legal; rule evaluation
   decides whether follow-up is desirable.
7. Durable records are the recovery authority. Redis accelerates runtime access
   and may be rebuilt.
8. Failure to append a turn after business commit triggers compensation; it
   does not rerun the answer.

Compatibility evidence belongs under repo-path: `tests/contracts`.
