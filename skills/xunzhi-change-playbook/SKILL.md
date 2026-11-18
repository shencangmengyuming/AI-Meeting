---
name: xunzhi-change-playbook
description: Use when a Python backend change crosses modules, contracts, persistence, cache state, runtime behavior, or migration compatibility boundaries.
---

# Change Playbook

Read `references/cross-domain-checklist.md` before implementation when two or
more layers or domains change.

## Order

1. Name the business object and authoritative store.
2. State the external and internal contracts being changed.
3. Add failing tests at the affected boundary.
4. Implement the smallest vertical change.
5. Update affected Skills and anchors in the same commit.
6. Verify rollback, recovery, observability, and compatibility.

## Constraint

Java is a reviewed compatibility input, not a Python module map. Record adapted
decisions in the owning Python Skill.
