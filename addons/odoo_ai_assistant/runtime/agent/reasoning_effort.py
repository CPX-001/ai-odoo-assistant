"""Provider-neutral adaptive reasoning-depth routing.

The router intentionally does not call another model. It uses cheap host-visible structure before
each provider decision and lets the provider's previous neutral decisions/results become evidence
for later decisions. Provider adapters map the neutral tiers to their own model settings.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from .planning import measure_task_complexity

_AUTO_REASONING_TIERS = frozenset({"light", "balanced", "deep"})


@dataclass(frozen=True, slots=True)
class AutoReasoningRoute:
    tier: str
    complexity_score: int
    reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.tier not in _AUTO_REASONING_TIERS:
            raise ValueError("agent_auto_reasoning_tier_invalid")
        if type(self.complexity_score) is not int or not 0 <= self.complexity_score <= 8:
            raise ValueError("agent_auto_reasoning_complexity_invalid")
        if len(self.reasons) > 8 or any(
            not isinstance(reason, str) or not 1 <= len(reason) <= 64
            for reason in self.reasons
        ):
            raise ValueError("agent_auto_reasoning_reason_invalid")

    def payload(self) -> dict[str, object]:
        return {
            "tier": self.tier,
            "complexity_score": self.complexity_score,
            "reasons": list(self.reasons),
        }


def resolve_auto_reasoning_route(
    *,
    message: str,
    screen: Mapping[str, object] | None = None,
    working_items: Sequence[Mapping[str, object]] = (),
) -> AutoReasoningRoute:
    """Choose a neutral effort tier without spending a separate provider round-trip.

    The first decision is driven mostly by deterministic structural complexity. Later decisions can
    escalate because the model itself requested capabilities/effects, encountered errors or entered
    an explicit deliberate TaskPlan. This keeps routing generic while making it responsive to the
    actual agent trajectory instead of keyword-classifying business intent.
    """

    score = measure_task_complexity(message, screen=screen)
    kinds = [
        item.get("kind")
        for item in working_items
        if isinstance(item, Mapping) and isinstance(item.get("kind"), str)
    ]
    capability_results = kinds.count("capability_result")
    capability_errors = kinds.count("capability_error")
    effect_proposals = kinds.count("plan_step_proposed")
    interventions = kinds.count("user_intervention")
    deliberate = _deliberate_planning(working_items)

    reasons: list[str] = []
    if deliberate:
        reasons.append("deliberate_plan")
    if score >= 6:
        reasons.append("high_structural_complexity")
    elif score >= 3:
        reasons.append("moderate_structural_complexity")
    if capability_errors >= 2:
        reasons.append("repeated_capability_errors")
    elif capability_errors:
        reasons.append("capability_error")
    if capability_results >= 2:
        reasons.append("multi_evidence_turn")
    if effect_proposals >= 2:
        reasons.append("multi_effect_turn")
    if interventions:
        reasons.append("user_redirected_turn")

    if deliberate or score >= 6 or capability_errors >= 2:
        tier = "deep"
    elif (
        score >= 3
        or capability_results >= 2
        or effect_proposals >= 2
        or capability_errors >= 1
        or interventions >= 1
    ):
        tier = "balanced"
    else:
        tier = "light"
        if not reasons:
            reasons.append("latency_sensitive_default")
    return AutoReasoningRoute(tier=tier, complexity_score=score, reasons=tuple(reasons[:8]))


def _deliberate_planning(working_items: Sequence[Mapping[str, object]]) -> bool:
    for item in reversed(tuple(working_items)):
        if not isinstance(item, Mapping) or item.get("kind") != "host_planning_strategy":
            continue
        data = item.get("data")
        return isinstance(data, Mapping) and data.get("effective_mode") == "deliberate"
    return False


__all__ = ["AutoReasoningRoute", "resolve_auto_reasoning_route"]
