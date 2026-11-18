# Auth And User Migration Contract

Planned package boundary: `app/auth_user/` with API, application, domain, and
infrastructure modules separated by dependency direction.

Before implementation, capture compatibility fixtures under:

- repo-path: `tests/contracts`

Acceptance criteria:

1. Login and current-user behavior have request/response contract tests.
2. User-owned reads and writes reject cross-user access.
3. HTTP and WebSocket adapters share authorization semantics without sharing
   transport parsing code.
4. Database uniqueness remains the final authority for registration races;
   caches and probabilistic filters are only accelerators.
5. Every new route, model, cache key, and ownership rule is reflected in this
   Skill in the same change.
