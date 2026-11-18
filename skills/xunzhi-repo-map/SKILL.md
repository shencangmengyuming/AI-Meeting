---
name: xunzhi-repo-map
description: Use when a Python backend task needs routing to the correct module, entry point, domain Skill, or implementation status.
---

# Python Repository Map

Use this Skill first when the owning module is unclear, then switch to the
domain Skill before changing code.

## Route

1. Read `references/module-routing.md` to select the owning domain.
2. Read `references/foundation-map.md` for existing shared infrastructure.
3. Open the selected domain Skill and its relevant references.
4. Use `xunzhi-change-playbook` when a change crosses two or more domains.

## Constraints

- Treat this repository as the only Python implementation truth.
- Distinguish existing modules from planned migration boundaries.
- Adapt reviewed business contracts from Java; derive code anchors from Python.
- Update routing when a module becomes implemented or changes ownership.
