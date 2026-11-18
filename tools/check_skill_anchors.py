import argparse
import re
from dataclasses import dataclass, field
from pathlib import Path

ANCHOR_PATTERN = re.compile(
    r"(?P<kind>repo-path|route|redis-key):\s*`(?P<value>[^`]+)`"
)
REQUIRED_SKILL_NAMES = (
    "xunzhi-repo-map",
    "xunzhi-business-dictionary",
    "xunzhi-auth-user",
    "xunzhi-interview-domain",
    "xunzhi-agent-domain",
    "xunzhi-media-domain",
    "xunzhi-ai-runtime",
    "xunzhi-change-playbook",
    "xunzhi-debug-playbook",
)


@dataclass
class AnchorCheckResult:
    skills_checked: int = 0
    paths_checked: int = 0
    routes_checked: int = 0
    redis_keys_checked: int = 0
    errors: list[str] = field(default_factory=list)


def _source_text(repo_root: Path) -> str:
    chunks: list[str] = []
    app_root = repo_root / "app"
    if not app_root.is_dir():
        return ""
    for path in app_root.rglob("*"):
        if not path.is_file() or path.suffix != ".py":
            continue
        if any(part.startswith(".") for part in path.relative_to(repo_root).parts):
            continue
        chunks.append(path.read_text(encoding="utf-8", errors="ignore"))
    return "\n".join(chunks)


def _is_within_repo(repo_root: Path, candidate: Path) -> bool:
    try:
        candidate.relative_to(repo_root)
    except ValueError:
        return False
    return True


def check_skill_anchors(repo_root: Path) -> AnchorCheckResult:
    repo_root = repo_root.resolve()
    result = AnchorCheckResult()
    skills_root = repo_root / "skills"
    source_text: str | None = None
    if not skills_root.is_dir():
        result.errors.append("missing local skills directory: skills")
        return result

    for skill_name in REQUIRED_SKILL_NAMES:
        skill_entry = skills_root / skill_name / "SKILL.md"
        if skill_entry.is_file():
            result.skills_checked += 1
        else:
            result.errors.append(
                f"missing required Skill: skills/{skill_name}/SKILL.md"
            )

    for markdown in skills_root.rglob("*.md"):
        content = markdown.read_text(encoding="utf-8")
        for match in ANCHOR_PATTERN.finditer(content):
            kind = match.group("kind")
            value = match.group("value")
            location = markdown.relative_to(repo_root)
            if kind == "repo-path":
                result.paths_checked += 1
                candidate = (repo_root / value).resolve()
                if not _is_within_repo(repo_root, candidate):
                    result.errors.append(
                        f"{location}: path escapes repository {value}"
                    )
                elif not candidate.exists():
                    result.errors.append(f"{location}: missing path {value}")
            elif kind == "route":
                result.routes_checked += 1
                if source_text is None:
                    source_text = _source_text(repo_root)
                route_path = value.split(maxsplit=1)[-1]
                if route_path not in source_text:
                    result.errors.append(f"{location}: stale route {value}")
            else:
                result.redis_keys_checked += 1
                if not value.strip():
                    result.errors.append(f"{location}: empty Redis Key anchor")
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    result = check_skill_anchors(parse_args().repo_root)
    print(
        "checked "
        f"skills={result.skills_checked} "
        f"paths={result.paths_checked} "
        f"routes={result.routes_checked} "
        f"redis_keys={result.redis_keys_checked}"
    )
    for error in result.errors:
        print(error)
    return 1 if result.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
