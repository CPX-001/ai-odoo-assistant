"""Provider-neutral planning strategy and TaskPlan replan guardrails."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Mapping

from ..capabilities import CapabilityContext
from .contracts import NextDecision, PlanStepProposal, ReasoningCapabilityCall, TaskPlanUpdate
from .decision_validation import NextDecisionValidationError
from .task_plan import TaskPlan, TaskPlanError, parse_task_plan

_PLANNING_MODES = frozenset({"adaptive", "deliberate", "auto"})
_EFFECTIVE_MODES = frozenset({"adaptive", "deliberate"})
_REPLAN_EVIDENCE_KINDS = frozenset(
    {"capability_result", "capability_error", "verified_effect_receipt"}
)
_LIST_ITEM_RE = re.compile(r"(?m)^\s*(?:[-*]|\d+[.)])\s+")


class PlanningStrategyError(RuntimeError):
    def __init__(self, code: str = "agent_planning_strategy_invalid") -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class PlanningStrategy:
    """Host-selected planning behavior; it never grants capability authority."""

    requested_mode: str
    effective_mode: str
    complexity_score: int
    task_plan_required: bool

    def payload(self) -> dict[str, object]:
        return {
            "requested_mode": self.requested_mode,
            "effective_mode": self.effective_mode,
            "complexity_score": self.complexity_score,
            "task_plan_required": self.task_plan_required,
        }


def resolve_planning_strategy(
    requested_mode: str | None,
    *,
    message: str,
    screen: Mapping[str, object] | None = None,
) -> PlanningStrategy:
    """Resolve the host strategy without classifying business intent.

    ``auto`` uses only bounded structural complexity signals. The score is an ergonomic planning
    hint, not policy/ACL/tool authority and therefore cannot enable an otherwise unavailable action.
    """

    mode = requested_mode or "adaptive"
    if mode not in _PLANNING_MODES:
        raise PlanningStrategyError()
    score = measure_task_complexity(message, screen=screen)
    effective = "deliberate" if mode == "deliberate" else "adaptive"
    if mode == "auto" and score >= 4:
        effective = "deliberate"
    return PlanningStrategy(
        requested_mode=mode,
        effective_mode=effective,
        complexity_score=score,
        task_plan_required=effective == "deliberate",
    )


def measure_task_complexity(
    message: str,
    *,
    screen: Mapping[str, object] | None = None,
) -> int:
    """Return a small deterministic 0..8 structural complexity score."""

    if not isinstance(message, str) or "\x00" in message:
        raise PlanningStrategyError()
    text = message.strip()
    score = 0
    if len(text) >= 160:
        score += 1
    if len(text) >= 600:
        score += 1
    if len([line for line in text.splitlines() if line.strip()]) >= 4:
        score += 1
    if len(_LIST_ITEM_RE.findall(text)) >= 2:
        score += 1
    if sum(text.count(mark) for mark in ".?!") >= 4:
        score += 1

    selected_ids = screen.get("selected_ids") if isinstance(screen, Mapping) else None
    if isinstance(selected_ids, list):
        if len(selected_ids) >= 2:
            score += 2
        if len(selected_ids) >= 20:
            score += 1
    return min(score, 8)


def planning_strategy_from_context(context: CapabilityContext) -> PlanningStrategy:
    raw = context.metadata.get("planning_strategy")
    if raw is None:
        return resolve_planning_strategy("adaptive", message="", screen=context.screen)
    return parse_planning_strategy(raw)


def parse_planning_strategy(value: object) -> PlanningStrategy:
    if not isinstance(value, dict) or set(value) != {
        "requested_mode",
        "effective_mode",
        "complexity_score",
        "task_plan_required",
    }:
        raise PlanningStrategyError()
    requested = value.get("requested_mode")
    effective = value.get("effective_mode")
    score = value.get("complexity_score")
    required = value.get("task_plan_required")
    if (
        requested not in _PLANNING_MODES
        or effective not in _EFFECTIVE_MODES
        or type(score) is not int
        or not 0 <= score <= 8
        or type(required) is not bool
        or required != (effective == "deliberate")
        or (requested == "adaptive" and effective != "adaptive")
        or (requested == "deliberate" and effective != "deliberate")
    ):
        raise PlanningStrategyError()
    if requested == "auto" and effective != ("deliberate" if score >= 4 else "adaptive"):
        raise PlanningStrategyError()
    return PlanningStrategy(requested, effective, score, required)


def validate_task_plan_transition(
    plan: TaskPlan,
    working_items: tuple[dict[str, object], ...],
) -> None:
    """Differentiate a state update from an evidence-driven structural replan."""

    previous_index, previous = _latest_task_plan(working_items)
    kind = plan.effective_revision_kind
    if previous is None:
        if plan.revision != 1 or kind != "initial":
            raise NextDecisionValidationError("agent_task_plan_revision_invalid")
        return

    if plan.revision != previous.revision + 1 or kind == "initial":
        raise NextDecisionValidationError("agent_task_plan_revision_invalid")
    if kind == "progress":
        if not _same_plan_structure(previous, plan):
            raise NextDecisionValidationError("agent_task_plan_replan_required")
        return
    if kind != "replan":
        raise NextDecisionValidationError("agent_task_plan_revision_invalid")
    if not _has_replan_evidence(working_items, after_index=previous_index):
        raise NextDecisionValidationError("agent_task_plan_replan_without_evidence")


class PlanningDecisionEngine:
    """Host wrapper enforcing planning-mode semantics around any provider adapter."""

    def __init__(self, provider) -> None:
        self._provider = provider

    async def next_decision(self, **kwargs) -> NextDecision:
        context = kwargs.get("context")
        working_items = kwargs.get("working_items", ())
        if not isinstance(context, CapabilityContext):
            raise PlanningStrategyError()
        if not isinstance(working_items, tuple):
            working_items = tuple(working_items)
        strategy = planning_strategy_from_context(context)
        decision = await self._provider.next_decision(**kwargs)

        _index, current_plan = _latest_task_plan(working_items)
        if (
            strategy.task_plan_required
            and current_plan is None
            and isinstance(decision, (ReasoningCapabilityCall, PlanStepProposal))
        ):
            raise NextDecisionValidationError("agent_task_plan_required", decision)
        if isinstance(decision, TaskPlanUpdate):
            validate_task_plan_transition(decision.task_plan, working_items)
        return decision


def _latest_task_plan(
    working_items: tuple[dict[str, object], ...],
) -> tuple[int, TaskPlan | None]:
    for index in range(len(working_items) - 1, -1, -1):
        item = working_items[index]
        if not isinstance(item, dict) or item.get("kind") != "task_plan":
            continue
        data = item.get("data")
        try:
            return index, parse_task_plan(dict(data) if isinstance(data, dict) else data)
        except TaskPlanError as error:
            raise NextDecisionValidationError(error.code) from error
    return -1, None


def _same_plan_structure(previous: TaskPlan, current: TaskPlan) -> bool:
    if previous.goal != current.goal or len(previous.steps) != len(current.steps):
        return False
    for left, right in zip(previous.steps, current.steps, strict=True):
        if (
            left.step_id != right.step_id
            or left.title != right.title
            or left.depends_on != right.depends_on
        ):
            return False
    return True


def _has_replan_evidence(
    working_items: tuple[dict[str, object], ...],
    *,
    after_index: int,
) -> bool:
    return any(
        isinstance(item, dict) and item.get("kind") in _REPLAN_EVIDENCE_KINDS
        for item in working_items[after_index + 1 :]
    )
