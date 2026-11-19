# Follow-up and Flow Contract

`app/interview/domain/follow_up.py` decides whether a follow-up is desirable.
`app/interview/domain/flow.py` decides whether the resulting state transition
is legal. Keep these responsibilities separate.

## Rule Order

Rules use Java defaults `maxFollowUp=2` and `lowScoreThreshold=60`:

1. A completed interview terminates with no follow-up.
2. Reaching the follow-up limit terminates with no follow-up.
3. `follow_up_needed=true` requests a follow-up.
4. A score below 60 requests a follow-up.
5. Missing points or a non-blank follow-up hint request a follow-up.
6. Otherwise, continue to the next main question.

The first matching positive reason is retained. The Provider flag therefore
has priority over low score and missing points.

## Follow-up Generation

`XunfeiFollowUpAgent` resolves `面试提问官` from MySQL `agent_properties` and
sends XingChen workflow parameters `mode=FOLLOW_UP`, `follow_up_count`,
`max_follow_up`, `question`, `AGENT_USER_INPUT`, and `resume_context`.

Follow-up numbers use `{mainQuestionNumber}-F{count}`, for example `1-F1` and
`1-F2`. The generated response reads `ask_to_user`; `end_interview=true`
suppresses it. Provider or parsing failure falls back to the scorer's
`follow_up_question`. With no usable fallback, advance the main question.

## Score Invariant

Only main-question answers add to `totalScore`. A follow-up answer is evaluated
and logged but does not add its score again.

## Legal States

| Source | Legal targets |
|---|---|
| `INIT` | `ASKING`, `COMPLETED` |
| `ASKING` | `EVALUATING`, `FOLLOW_UP`, `COMPLETED` |
| `EVALUATING` | `ASKING`, `FOLLOW_UP`, `COMPLETED` |
| `FOLLOW_UP` | `EVALUATING`, `ASKING`, `COMPLETED` |
| `COMPLETED` | none |

Starting a follow-up keeps `currentIndex`, increments `followUpCount`, and sets
`currentQuestionNumber` to the `-F` number. Advancing a main question resets
`followUpCount`; advancing past the last main question clears the current
question and enters `COMPLETED`.
