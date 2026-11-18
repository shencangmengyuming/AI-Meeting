---
name: xunzhi-business-dictionary
description: Use when Python backend work depends on shared business terms, identifiers, truth sources, lifecycle meanings, or compatibility vocabulary.
---

# Business Dictionary

Read `references/object-dictionary.md` before changing a contract whose nouns
span domains.

## Constraints

- Identify the authoritative store before changing an object.
- Separate durable records, runtime state, snapshots, logs, and API views.
- Preserve identifier meaning across retries and service boundaries.
- Record new cross-domain terminology here; keep implementation detail in the
  owning domain Skill.
