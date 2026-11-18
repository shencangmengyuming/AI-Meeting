# Python Foundation Review

## Review Gate

- FastAPI application resources are created by lifespan and explicitly closed.
- SQLAlchemy creates one `AsyncSession` per scope and rolls back failed scopes.
- Java-compatible `Result` fields and error codes are covered by golden tests.
- MySQL, MongoDB and Redis adapters are exercised against real containers.
- Configuration contains no working third-party credentials or production secrets.
- Docker health and shutdown behavior are verified before module migration.
- The repository owns nine Python Skills under `skills/`; Java Skills are not
  used as Python implementation truth.
- Skill validation requires the complete local catalog, rejects paths outside
  this repository, and verifies production routes from `app/**/*.py` only.

## Rollback

Foundation introduces no routed business endpoint. Rollback consists of stopping
the Python container; Java remains the only production backend until later
module canaries explicitly change gateway routing.
