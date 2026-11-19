from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from app.interview.domain.follow_up import (
    FollowUpRuleContext,
    FollowUpRuleDecision,
)

RuleNode = Callable[["RuleExecution"], None]


@dataclass
class RuleExecution:
    context: FollowUpRuleContext
    resolved_max_follow_up: int
    default_low_score_threshold: int
    need_follow_up: bool | None = None
    reason_code: str | None = None
    reason_text: str | None = None
    terminal: bool = False

    def decide(
        self,
        need_follow_up: bool,
        reason_code: str,
        reason_text: str,
        *,
        terminal: bool = True,
    ) -> None:
        if self.reason_code is not None:
            return
        self.need_follow_up = need_follow_up
        self.reason_code = reason_code
        self.reason_text = reason_text
        self.terminal = terminal


class FollowUpRuleChain:
    def __init__(
        self,
        *,
        chain_id: str,
        rule_version: str,
        node_names: Sequence[str],
        nodes: Mapping[str, RuleNode] | None = None,
        default_max_follow_up: int = 2,
        default_low_score_threshold: int = 60,
    ) -> None:
        self.chain_id = chain_id
        self.rule_version = rule_version
        self.node_names = tuple(node_names)
        self.nodes = dict(nodes or default_rule_nodes())
        self.default_max_follow_up = max(default_max_follow_up, 1)
        self.default_low_score_threshold = max(default_low_score_threshold, 0)

    @classmethod
    def from_file(
        cls,
        path: Path,
        *,
        chain_id: str = "default_followup_chain",
    ) -> "FollowUpRuleChain":
        try:
            root = yaml.safe_load(path.read_text(encoding="utf-8"))
            chains = _mapping(root).get("chains")
            chain = _mapping(_mapping(chains).get(chain_id))
            version = str(chain.get("version") or "v1.0.0")
            raw_nodes = chain.get("nodes")
            node_names = tuple(str(node) for node in _sequence(raw_nodes))
            if not node_names:
                raise ValueError("rule chain has no nodes")
            return cls(
                chain_id=chain_id,
                rule_version=version,
                node_names=node_names,
            )
        except Exception:
            return cls(
                chain_id=chain_id,
                rule_version="invalid",
                node_names=("invalid_configuration",),
            )

    @classmethod
    def default(cls) -> "FollowUpRuleChain":
        path = Path(__file__).resolve().parents[1] / "config" / "followup_rules.yaml"
        return cls.from_file(path)

    def decide(self, context: FollowUpRuleContext) -> FollowUpRuleDecision:
        resolved_max = (
            context.max_follow_up
            if context.max_follow_up > 0
            else self.default_max_follow_up
        )
        execution = RuleExecution(
            context=context,
            resolved_max_follow_up=resolved_max,
            default_low_score_threshold=self.default_low_score_threshold,
        )
        try:
            for node_name in self.node_names:
                node = self.nodes[node_name]
                node(execution)
                if execution.terminal:
                    break
            if execution.reason_code is None:
                _finalize_decision(execution)
            return FollowUpRuleDecision(
                need_follow_up=bool(execution.need_follow_up),
                reason_code=execution.reason_code or "NO_RULE_TRIGGER",
                reason_text=execution.reason_text or "no follow-up trigger matched",
                resolved_max_follow_up=resolved_max,
                chain_id=self.chain_id,
                rule_version=self.rule_version,
            )
        except Exception:
            return FollowUpRuleDecision(
                need_follow_up=False,
                reason_code="RULE_CHAIN_FALLBACK",
                reason_text="follow-up rule chain failed open",
                resolved_max_follow_up=resolved_max,
                chain_id=self.chain_id,
                rule_version=self.rule_version,
                fallback=True,
            )


def default_rule_nodes() -> dict[str, RuleNode]:
    return {
        "load_context": _load_context,
        "completed_state_guard": _completed_state_guard,
        "followup_limit_guard": _followup_limit_guard,
        "ai_suggestion_judge": _ai_suggestion_judge,
        "low_score_judge": _low_score_judge,
        "missing_points_judge": _missing_points_judge,
        "finalize_decision": _finalize_decision,
    }


def _load_context(execution: RuleExecution) -> None:
    return None


def _completed_state_guard(execution: RuleExecution) -> None:
    if execution.context.interview_completed:
        execution.decide(
            False,
            "INTERVIEW_COMPLETED",
            "interview already completed",
        )


def _followup_limit_guard(execution: RuleExecution) -> None:
    if execution.context.follow_up_count >= execution.resolved_max_follow_up:
        execution.decide(
            False,
            "FOLLOW_UP_LIMIT_REACHED",
            "follow-up limit reached",
        )


def _ai_suggestion_judge(execution: RuleExecution) -> None:
    if execution.context.follow_up_needed_from_ai:
        execution.decide(
            True,
            "AI_SUGGESTED",
            "follow-up suggested by ai result",
        )


def _low_score_judge(execution: RuleExecution) -> None:
    threshold = (
        execution.context.low_score_threshold
        if execution.context.low_score_threshold >= 0
        else execution.default_low_score_threshold
    )
    score = execution.context.score
    if score is not None and score < threshold:
        execution.decide(
            True,
            "LOW_SCORE",
            f"score below threshold: {score} < {threshold}",
        )


def _missing_points_judge(execution: RuleExecution) -> None:
    hint = execution.context.follow_up_question_hint
    if execution.context.missing_points or bool(hint and hint.strip()):
        execution.decide(
            True,
            "MISSING_POINTS",
            "missing points or follow-up hint detected",
        )


def _finalize_decision(execution: RuleExecution) -> None:
    execution.decide(
        False,
        "NO_RULE_TRIGGER",
        "no follow-up trigger matched",
    )


def _mapping(value: Any) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("expected mapping")
    return value


def _sequence(value: Any) -> Sequence[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError("expected sequence")
    return value
