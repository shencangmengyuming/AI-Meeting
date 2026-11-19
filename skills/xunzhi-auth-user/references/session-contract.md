# Python Session Contract

Package boundary: `app/auth_user/` with domain contracts separated from Redis
infrastructure.

- Token key: `ai-meeting:auth:token:{token}`
- Session key: `ai-meeting:auth:session:{username}`
- Timeout: 2,592,000 seconds by default.
- Login is atomic and reuses an active session token for the same username.
- Resolving a token does not refresh its TTL.
- Logout atomically removes the token and session keys.
- User identity is loaded through `AuthIdentityLookup`; Redis only stores the
  session-to-username association.
- Login reads the existing `t_user.password` value through a credential lookup,
  verifies it with constant-time comparison, and then issues a Python token.
- Existing plaintext passwords are verified once and upgraded after successful
  login to the versioned `scrypt$...` format; failed logins never rewrite data.
- Registration checks username availability through RedisBloom when available,
  falls back to MySQL, serializes the username with a short Redis lock, relies
  on the MySQL unique index as the final authority, and updates the filter only
  after a successful commit.
- Python owns this contract. It does not read or write Java Sa-Token records.

Acceptance criteria:

1. Login, resolve, logout, expiration, and concurrent login have contract tests.
2. User-owned reads and writes reject cross-user access.
3. HTTP and WebSocket adapters share authorization semantics without sharing
   transport parsing code.
4. Database uniqueness remains the final authority for registration races.
5. Every new route, model, cache key, and ownership rule is reflected in this
   Skill in the same change.
