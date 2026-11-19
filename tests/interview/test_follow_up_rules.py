import importlib
from pathlib import Path
from typing import Any


def follow_up_module() -> Any:
    return importlib.import_module("app.interview.domain.follow_up")


def rule_chain_module() -> Any:
    return importlib.import_module("app.interview.application.followup_rules")


def context(**overrides: object) -> Any:
    follow_up = follow_up_module()
    values: dict[str, object] = {
        "score": 80,
        "missing_points": (),
        "follow_up_needed_from_ai": False,
        "follow_up_question_hint": None,
        "follow_up_count": 0,
        "max_follow_up": 2,
        "interview_completed": False,
        "low_score_threshold": 60,
    }
    values.update(overrides)
    return follow_up.FollowUpRuleContext(**values)


def test_completed_interview_never_requests_follow_up() -> None:
    follow_up = follow_up_module()

    decision = follow_up.FollowUpRuleService().decide(
        context(interview_completed=True, follow_up_needed_from_ai=True)
    )

    assert decision.need_follow_up is False
    assert decision.reason_code == "INTERVIEW_COMPLETED"


def test_follow_up_limit_stops_all_later_rules() -> None:
    follow_up = follow_up_module()

    decision = follow_up.FollowUpRuleService().decide(
        context(
            follow_up_count=2,
            max_follow_up=2,
            score=20,
            missing_points=("transactions",),
            follow_up_needed_from_ai=True,
        )
    )

    assert decision.need_follow_up is False
    assert decision.reason_code == "FOLLOW_UP_LIMIT_REACHED"
    assert decision.resolved_max_follow_up == 2


def test_ai_suggestion_has_priority_over_low_score_and_missing_points() -> None:
    follow_up = follow_up_module()

    decision = follow_up.FollowUpRuleService().decide(
        context(
            score=20,
            missing_points=("transactions",),
            follow_up_needed_from_ai=True,
        )
    )

    assert decision.need_follow_up is True
    assert decision.reason_code == "AI_SUGGESTED"


def test_low_score_requests_follow_up_below_java_threshold() -> None:
    follow_up = follow_up_module()

    decision = follow_up.FollowUpRuleService().decide(context(score=59))

    assert decision.need_follow_up is True
    assert decision.reason_code == "LOW_SCORE"


def test_missing_points_request_follow_up_for_otherwise_good_answer() -> None:
    follow_up = follow_up_module()

    decision = follow_up.FollowUpRuleService().decide(
        context(score=90, missing_points=("monitoring",))
    )

    assert decision.need_follow_up is True
    assert decision.reason_code == "MISSING_POINTS"


def test_no_trigger_returns_no_follow_up_and_uses_default_maximum() -> None:
    follow_up = follow_up_module()

    decision = follow_up.FollowUpRuleService().decide(
        context(score=60, max_follow_up=0)
    )

    assert decision.need_follow_up is False
    assert decision.reason_code == "NO_RULE_TRIGGER"
    assert decision.resolved_max_follow_up == 2


def test_rule_order_is_loaded_from_configuration(tmp_path: Path) -> None:
    rules = tmp_path / "followup_rules.yaml"
    rules.write_text(
        """
chains:
  custom_chain:
    version: v2
    nodes:
      - load_context
      - missing_points_judge
      - ai_suggestion_judge
      - finalize_decision
""".strip(),
        encoding="utf-8",
    )
    chain = rule_chain_module().FollowUpRuleChain.from_file(
        rules,
        chain_id="custom_chain",
    )

    decision = chain.decide(
        context(
            missing_points=("transactions",),
            follow_up_needed_from_ai=True,
        )
    )

    assert decision.need_follow_up is True
    assert decision.reason_code == "MISSING_POINTS"
    assert decision.chain_id == "custom_chain"
    assert decision.rule_version == "v2"


def test_invalid_rule_configuration_fails_open(tmp_path: Path) -> None:
    rules = tmp_path / "followup_rules.yaml"
    rules.write_text(
        """
chains:
  broken_chain:
    version: broken
    nodes:
      - load_context
      - node_that_is_not_registered
""".strip(),
        encoding="utf-8",
    )
    chain = rule_chain_module().FollowUpRuleChain.from_file(
        rules,
        chain_id="broken_chain",
    )

    decision = chain.decide(context(follow_up_needed_from_ai=True))

    assert decision.need_follow_up is False
    assert decision.reason_code == "RULE_CHAIN_FALLBACK"
    assert decision.fallback is True
    assert decision.chain_id == "broken_chain"
