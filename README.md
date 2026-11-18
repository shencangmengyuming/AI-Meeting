# AI Meeting Backend

Python FastAPI backend for the AI Meeting migration. The service is built as a
modular monolith and is introduced alongside the existing Java backend.

## Local checks

```bash
python -m pytest -v
python -m ruff check .
python -m pyright
python tools/check_skill_anchors.py --repo-root .
```

Project knowledge for coding agents lives in `skills/`. It is maintained from
the Python implementation and compatibility tests in this repository; the Java
repository is a migration reference, not the Python Skill source.
