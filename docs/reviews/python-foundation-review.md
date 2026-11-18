# Python Foundation Review

## Review Gate

- FastAPI application resources are created by lifespan and explicitly closed.
- SQLAlchemy creates one `AsyncSession` per scope and rolls back failed scopes.
- Java-compatible `Result` fields and error codes are covered by golden tests.
- MySQL, MongoDB and Redis adapters are exercised against real containers.
- Configuration contains no working third-party credentials or production secrets.
- Docker health and shutdown behavior are verified before module migration.
- Skill anchor validation is unit-tested in this repository and scans the Java
  Skill source locally when both repositories are checked out as siblings.

## Rollback

Foundation introduces no routed business endpoint. Rollback consists of stopping
the Python container; Java remains the only production backend until later
module canaries explicitly change gateway routing.
