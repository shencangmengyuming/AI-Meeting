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
# Python Answer Pipeline Status

The first vertical slice is implemented in
`app/interview/application/answers.py`:

1. Normalize or derive `requestId`.
2. Replay a committed response for the same request.
3. Acquire a session/question Redis lock.
4. Verify session ownership and the active question number.
5. Call the replaceable `InterviewScoringAgent` and require a normalized
   `ScoringResult` with a score in `[0, 100]`.
6. Run `FollowUpRuleService`; ask `InterviewFlowStateMachine` to enter
   `FOLLOW_UP`, advance the main question, or complete the flow.
7. Append a durable `interview_turn` document with score and feedback.
8. Persist the Redis flow state and cache the response for idempotent replay.

The scoring Provider remains an infrastructure adapter. The default runtime
adapter is `XunfeiScoringAgent`; it resolves the scoring workflow from MySQL
and fails explicitly when configuration, transport, or score parsing fails. It
must never invent a local score. Read `scoring-provider.md` before changing its
request or response contract.

Score commit compensation and runtime snapshots remain future steps and must
not bypass idempotency or question-lock boundaries.
