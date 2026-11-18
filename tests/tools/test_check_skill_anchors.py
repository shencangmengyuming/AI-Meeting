from pathlib import Path

from tools.check_skill_anchors import REQUIRED_SKILL_NAMES, check_skill_anchors


def _write_skill_catalog(repo_root: Path) -> None:
    for skill_name in REQUIRED_SKILL_NAMES:
        skill = repo_root / "skills" / skill_name / "SKILL.md"
        skill.parent.mkdir(parents=True, exist_ok=True)
        skill.write_text(f"# {skill_name}\n", encoding="utf-8")


def test_validator_accepts_current_repository_paths_and_routes(
    tmp_path: Path,
) -> None:
    _write_skill_catalog(tmp_path)
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "main.py").write_text(
        'app.get("/actuator/health")', encoding="utf-8"
    )
    skill = tmp_path / "skills" / "xunzhi-repo-map" / "SKILL.md"
    skill.write_text(
        "\n".join(
            [
                "repo-path: `app/main.py`",
                "route: `GET /actuator/health`",
                "redis-key: `session:{id}`",
            ]
        ),
        encoding="utf-8",
    )

    result = check_skill_anchors(tmp_path)

    assert result.errors == []
    assert result.skills_checked == len(REQUIRED_SKILL_NAMES)
    assert result.paths_checked == 1
    assert result.routes_checked == 1
    assert result.redis_keys_checked == 1


def test_validator_reports_missing_path_and_stale_route(tmp_path: Path) -> None:
    _write_skill_catalog(tmp_path)
    skill = tmp_path / "skills" / "xunzhi-repo-map" / "SKILL.md"
    skill.write_text(
        "repo-path: `missing.py`\nroute: `POST /api/missing`\n",
        encoding="utf-8",
    )

    result = check_skill_anchors(tmp_path)

    assert any("missing.py" in error for error in result.errors)
    assert any("POST /api/missing" in error for error in result.errors)


def test_validator_requires_the_local_python_skill_catalog(tmp_path: Path) -> None:
    java_skill = tmp_path / "AI-Meeting" / "skills" / "xunzhi-repo-map" / "SKILL.md"
    java_skill.parent.mkdir(parents=True)
    java_skill.write_text("repo-path: `AI-Meeting/pom.xml`\n", encoding="utf-8")
    (tmp_path / "AI-Meeting" / "pom.xml").write_text("", encoding="utf-8")

    result = check_skill_anchors(tmp_path)

    assert result.skills_checked == 0
    assert result.paths_checked == 0
    assert result.errors == ["missing local skills directory: skills"]


def test_validator_requires_all_nine_python_skills(tmp_path: Path) -> None:
    _write_skill_catalog(tmp_path)
    missing = "xunzhi-media-domain"
    (tmp_path / "skills" / missing / "SKILL.md").unlink()

    result = check_skill_anchors(tmp_path)

    assert f"missing required Skill: skills/{missing}/SKILL.md" in result.errors


def test_validator_rejects_repo_paths_outside_current_repository(
    tmp_path: Path,
) -> None:
    _write_skill_catalog(tmp_path)
    sibling_file = tmp_path.parent / "AI-Meeting" / "pom.xml"
    sibling_file.parent.mkdir(exist_ok=True)
    sibling_file.write_text("", encoding="utf-8")
    skill = tmp_path / "skills" / "xunzhi-repo-map" / "SKILL.md"
    skill.write_text("repo-path: `../AI-Meeting/pom.xml`\n", encoding="utf-8")

    result = check_skill_anchors(tmp_path)

    assert any("path escapes repository" in error for error in result.errors)


def test_validator_does_not_use_java_sources_as_python_route_truth(
    tmp_path: Path,
) -> None:
    _write_skill_catalog(tmp_path)
    (tmp_path / "legacy").mkdir()
    (tmp_path / "legacy" / "Controller.java").write_text(
        '@GetMapping("/legacy-only")', encoding="utf-8"
    )
    skill = tmp_path / "skills" / "xunzhi-repo-map" / "SKILL.md"
    skill.write_text("route: `GET /legacy-only`\n", encoding="utf-8")

    result = check_skill_anchors(tmp_path)

    assert any("stale route GET /legacy-only" in error for error in result.errors)


def test_validator_does_not_use_tests_as_python_route_truth(tmp_path: Path) -> None:
    _write_skill_catalog(tmp_path)
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_routes.py").write_text(
        'client.get("/test-only")', encoding="utf-8"
    )
    skill = tmp_path / "skills" / "xunzhi-repo-map" / "SKILL.md"
    skill.write_text("route: `GET /test-only`\n", encoding="utf-8")

    result = check_skill_anchors(tmp_path)

    assert any("stale route GET /test-only" in error for error in result.errors)
