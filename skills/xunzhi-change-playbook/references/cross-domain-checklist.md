# Cross-domain Checklist

For every affected item, identify owner, test, migration, and rollback:

- HTTP or WebSocket contract
- application command/query boundary
- domain invariant and state transition
- MySQL or MongoDB schema/index
- Redis key, TTL, lock, or Lua contract
- AI prompt/output schema and parser
- background task, retry, compensation, or shutdown behavior
- logging, metrics, tracing, and secret redaction
- compatibility fixture
- Skill reference and executable anchor

Foundation quality gates are defined in:

- repo-path: `.github/workflows/python-backend.yml`
- repo-path: `pyproject.toml`
- repo-path: `tools/check_skill_anchors.py`

Do not consider a cross-domain migration complete while its rollback path or
authoritative recovery source is undefined.
