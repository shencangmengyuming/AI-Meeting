# Scoring Provider Contract

The default answer scorer is `XunfeiScoringAgent` in
`app/interview/infrastructure/scoring.py`. It is an infrastructure adapter for
the domain-level `InterviewScoringAgent` protocol.

## Agent Binding

Resolve active rows from MySQL `agent_properties` in this order:

1. `用户答案评分官`
2. `面试答案评分官`

Required fields are `id`, `agent_name`, `api_key`, `api_secret`, and
`api_flow_id`. Missing or blank values fail the scoring request. Credentials
stay in MySQL and must not appear in source, fixtures, logs, or documentation.

## Xunfei Workflow Request

Send a non-streaming `POST` to the XingChen workflow completions endpoint with:

- authorization `Bearer {api_key}:{api_secret}`;
- `flow_id` from `api_flow_id`;
- `chat_id` equal to `{session_id}_score`;
- empty `history`;
- parameters `AGENT_USER_INPUT`, `question`, and empty `resume_context`.

## Response Normalization

Accept scoring JSON from the root, `choices[0].delta.content`,
`choices[0].message.content`, or root `content`. String content may use a
Markdown JSON fence, surrounding prose, or a nested object/string field named
`json`.

Normalize these Java-compatible aliases:

| Result | Accepted keys |
|---|---|
| score | `score`, `total_score`, `composite_score` |
| feedback | `feedback`, `comment`, `suggestion` |
| missing points | `missing_points`, `missingPoints`, `lack_points` |
| follow-up flag | `follow_up_needed`, `followUpNeeded` |
| follow-up question | `follow_up_question`, `followUpQuestion`, `ask_to_user`, `ask` |

Round numeric scores with Java `Math.round` semantics and clamp them to
`0..100` before constructing `ScoringResult`. A non-zero Provider `code`,
non-200 HTTP response, malformed body, or missing score raises business error
`B000001`; the answer pipeline must not append a turn or advance flow.
