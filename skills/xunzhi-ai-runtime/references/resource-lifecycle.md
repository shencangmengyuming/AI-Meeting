# Resource Lifecycle

Current runtime foundation:

- repo-path: `app/core/lifespan.py`
- repo-path: `app/core/settings.py`
- repo-path: `app/infrastructure/http.py`
- repo-path: `app/infrastructure/mysql.py`
- repo-path: `app/infrastructure/mongodb.py`
- repo-path: `app/infrastructure/redis.py`

Application lifespan creates shared connection pools and clients once per app.
Request-scoped code borrows them through explicit dependencies. Domain modules
must not instantiate replacement global clients or close shared resources.

Shutdown must stop owned background tasks before closing the resources those
tasks use.
