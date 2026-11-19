# AI Meeting Backend

Independent Python FastAPI backend for AI Meeting. The service is built as a
modular monolith; Java is used only as a reviewed business reference.

## Start locally

Docker Compose starts the Python API, MySQL, MongoDB and Redis. The application
creates its required MySQL tables and MongoDB indexes idempotently at startup.

```bash
docker compose up -d --build
curl --noproxy '*' http://127.0.0.1:8000/actuator/health
```

The API is available at `http://127.0.0.1:8000`; interactive OpenAPI docs are
at `http://127.0.0.1:8000/docs`.

To enable Xunfei ASR/TTS, copy `.env.example` to `.env` and fill in the six
provider variables before starting Compose. This Python `.env` is the sole
runtime source for ASR/TTS application credentials; Java configuration files
are not read or required. AI and Agent workflow credentials are managed in the
`ai_properties` and `agent_properties` tables through the authenticated
configuration APIs.

The first local user can be registered through
`POST /api/xunzhi/v1/users/register`. To make that user the initial local
administrator, run:

```bash
docker compose exec mysql mysql -uai_meeting -plocal_only ai_meeting \
  -e "INSERT INTO admin_permission(username,is_admin,del_flag) \
      VALUES('YOUR_USERNAME',1,0) ON DUPLICATE KEY UPDATE is_admin=1,del_flag=0;"
```

Stop the stack with `docker compose down`. Add `-v` only when intentionally
removing local MySQL, MongoDB and Redis data.

## Local checks

```bash
python -m pytest -v
python -m ruff check .
python -m pyright
python tools/check_skill_anchors.py --repo-root .
```

Project knowledge for coding agents lives in `skills/`. It is maintained from
the Python implementation; the Java repository is a business/reference source,
not a runtime dependency or Python Skill source.

The active architecture decision, implementation roadmap and module plans live
under [`docs/`](docs/README.md). Those plans are scoped to this independent
Python repository and include the current implementation status for each batch.
