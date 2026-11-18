# Foundation Map

The application factory owns FastAPI construction and the health contract:

- repo-path: `app/main.py`
- route: `GET /actuator/health`

The lifespan creates one application-scoped resource bundle for MySQL, MongoDB,
Redis, and outbound HTTP, then closes every resource on shutdown:

- repo-path: `app/core/lifespan.py`

Shared compatibility behavior is centralized instead of repeated by domains:

- Configuration: `app/core/settings.py`
- Result envelope: `app/core/result.py`
- Business and validation errors: `app/core/errors.py` and
  `app/core/exception_handlers.py`
- Request identifiers: `app/core/request_id.py`

Domain packages should depend on these interfaces and must not create global
clients during import.
