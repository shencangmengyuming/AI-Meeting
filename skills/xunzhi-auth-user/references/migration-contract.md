# Auth And User Migration Contract

Package boundary: `app/auth_user/` with API, application, domain, and
infrastructure modules separated by dependency direction.

## Verified Sa-Token Contract

- redis-key: `Authorization:login:token:{token}`
- redis-key: `Authorization:login:session:{username}`
- redis-key: `xunzhi:user:id:{username}`
- Timeout: 2,592,000 seconds.
- Shared login reuses one UUID token and refreshes both TTLs.
- Authenticated reads do not refresh the TTL.
- Logout deletes the two Sa-Token keys but leaves the legacy
  `xunzhi-agent:login:{username}` Hash untouched.
- Java Sa-Token 1.39.0 successfully reused a Session written by the Python
  adapter during the compatibility check.

The Sa-Token keys are authentication truth. The legacy login Hash belongs to
the user login workflow and must not be used to resolve the current principal.
The user ID cache is a 30-minute accelerator over `t_user`; `admin_permission`
remains the role source during this migration stage.

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
