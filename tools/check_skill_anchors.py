import argparse
import re
from dataclasses import dataclass, field
from pathlib import Path

ANCHOR_PATTERN = re.compile(
    r"(?P<kind>repo-path|route|redis-key):\s*`(?P<value>[^`]+)`"
)


@dataclass
class AnchorCheckResult:
    paths_checked: int = 0
    routes_checked: int = 0
    redis_keys_checked: int = 0
    errors: list[str] = field(default_factory=list)


def _source_text(repo_root: Path) -> str:
    suffixes = {".py", ".java", ".yml", ".yaml", ".xml"}
    chunks: list[str] = []
    for path in repo_root.rglob("*"):
        if not path.is_file() or path.suffix not in suffixes:
            continue
        if any(part.startswith(".") for part in path.relative_to(repo_root).parts):
            continue
        chunks.append(path.read_text(encoding="utf-8", errors="ignore"))
    return "\n".join(chunks)


def check_skill_anchors(repo_root: Path) -> AnchorCheckResult:
    repo_root = repo_root.resolve()
    result = AnchorCheckResult()
    skills_root = repo_root / "skills"
    source_text: str | None = None
    if not skills_root.exists() and (repo_root / "AI-Meeting" / "skills").exists():
        skills_root = repo_root / "AI-Meeting" / "skills"

    for markdown in skills_root.rglob("*.md"):
        content = markdown.read_text(encoding="utf-8")
        for match in ANCHOR_PATTERN.finditer(content):
            kind = match.group("kind")
            value = match.group("value")
            location = markdown.relative_to(repo_root)
            if kind == "repo-path":
                result.paths_checked += 1
                if not (repo_root / value).exists():
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
        f"paths={result.paths_checked} "
        f"routes={result.routes_checked} "
        f"redis_keys={result.redis_keys_checked}"
    )
    for error in result.errors:
        print(error)
    return 1 if result.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
