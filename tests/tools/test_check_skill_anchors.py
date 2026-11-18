from pathlib import Path

from tools.check_skill_anchors import check_skill_anchors


def test_validator_accepts_existing_paths_and_routes(tmp_path: Path) -> None:
    (tmp_path / "service" / "app").mkdir(parents=True)
    (tmp_path / "service" / "app" / "main.py").write_text("", encoding="utf-8")
    skill = tmp_path / "skills" / "example" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text(
        "\n".join(
            [
                "repo-path: `service/app/main.py`",
                "route: `GET /actuator/health`",
                "redis-key: `session:{id}`",
            ]
        ),
        encoding="utf-8",
    )
    (tmp_path / "service" / "app" / "routes.py").write_text(
        'app.get("/actuator/health")', encoding="utf-8"
    )

    result = check_skill_anchors(tmp_path)

    assert result.errors == []
    assert result.paths_checked == 1
    assert result.routes_checked == 1
    assert result.redis_keys_checked == 1


def test_validator_reports_missing_path_and_stale_route(tmp_path: Path) -> None:
    skill = tmp_path / "skills" / "example" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text(
        "repo-path: `missing.py`\nroute: `POST /api/missing`\n",
        encoding="utf-8",
    )

    result = check_skill_anchors(tmp_path)

    assert any("missing.py" in error for error in result.errors)
    assert any("POST /api/missing" in error for error in result.errors)
