# Python Skill Catalog

This directory is the knowledge layer for `AI-Meeting-backend` only. Java may
provide reviewed business meaning and compatibility requirements, but Java
files are not implementation truth for this repository.

Each Skill keeps routing and hard constraints in `SKILL.md`. Domain detail
lives in `references/`. Verifiable facts use these anchors:

- `repo-path`: a path that must exist inside this repository.
- `route`: a route that must exist in Python source.
- `redis-key`: a non-empty Redis key contract.

Run `python tools/check_skill_anchors.py --repo-root .` after changing Skills.
Update the affected Skill in the same change that alters a business contract,
module boundary, route, persistence model, Redis key, or recovery rule.
