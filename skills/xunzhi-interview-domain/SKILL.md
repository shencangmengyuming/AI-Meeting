---
name: xunzhi-interview-domain
description: Use when implementing or reviewing Python interview sessions, question generation, answer scoring, follow-up decisions, flow state, restoration, or finalization.
---

# Interview Domain

Session lifecycle, question reads, answer idempotency, question locking,
Xunfei scoring, follow-up rules, and flow transitions are implemented.
RuleChain, AI Guard, Heavy Lock, Single-flight and Runtime recovery cores are
implemented and tested. Turn write failures enter a bounded compensation queue,
and score/suggestion/radar reads aggregate committed turns. Resume extraction,
demeanor evaluation, Mongo CAS verification, atomic report finalization and
Lua-fenced Single-flight are implemented. See `docs/reviews/python-interview-review.md`.

## Order

1. Read `references/invariants.md`.
2. Read `references/answer-pipeline.md` for answer submission.
3. Read `references/scoring-provider.md` when changing scoring or Agent binding.
4. Read `references/follow-up-flow.md` when changing follow-up or flow state.
5. Add compatibility fixtures and failing tests.
6. Implement one vertical slice without bypassing the flow state.

## Constraints

- Keep session lifecycle and question-flow state distinct.
- Treat `request_id` as the answer idempotency boundary.
- Serialize concurrent submissions for the same question.
- Separate follow-up decision rules from legal state transitions.
- Load scoring credentials from `agent_properties`; keep them out of source and
  logs.
- Recovery and finalization are first-class contracts.

## Current Entry Points

- `app/interview/application/session.py`
- `app/interview/application/questions.py`
- `app/interview/application/answers.py`
- `app/interview/domain/scoring.py`
- `app/interview/domain/flow.py`
- `app/interview/domain/follow_up.py`
- `app/interview/application/followup_rules.py`
- `app/interview/application/ai_guard.py`
- `app/interview/application/heavy_lock.py`
- `app/interview/application/runtime_rehydrate.py`
- `app/interview/application/turn_compensation.py`
- `app/interview/application/reports.py`
- `app/interview/application/heavy_workflows.py`
- `app/interview/infrastructure/workflow.py`
- `app/ai_runtime/application/singleflight.py`
- `app/interview/domain/runtime.py`
- `app/interview/infrastructure/scoring.py`
- `app/interview/api/router.py`
- `app/interview/application/records.py`
- `app/interview/infrastructure/indexes.py`
- `tests/interview/test_session_routes.py`
- `tests/interview/test_question_routes.py`
- `tests/interview/test_answer_routes.py`
- `tests/interview/test_scoring_pipeline.py`
- `tests/interview/test_xunfei_scoring_agent.py`
- `tests/interview/test_flow_state_machine.py`
- `tests/interview/test_follow_up_rules.py`
- `tests/interview/test_xunfei_follow_up_agent.py`
