# Python Auth/User Review

Reviewed against the Java baseline and the Python implementation on 2026-11-19.

## Certified behavior

- Python owns bearer tokens and Redis session records; no Java Sa-Token compatibility is required.
- Login, logout, current-user resolution, permission checks, legacy password upgrade, profile routes and registration routes are covered by Python tests.
- Username availability uses Bloom fast rejection, while registration is serialized by username lock and protected by the database unique constraint.
- Bloom rebuild uses a temporary key and atomic rename, so a failed rebuild does not replace the live filter.

## Residual risks

- Redis/Bloom outages must remain observable through metrics and alerts; database checks are the correctness fallback.
- Production schema migration must provision the username unique index and the session indexes before enabling writes.

## Gate result

Run the Auth/User test suite, integration race test, Ruff, Pyright and Skill anchor validator together before release.
