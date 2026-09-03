"""Provider-neutral preparation and execution of typed capability EffectPlans."""

from __future__ import annotations

import hashlib
import inspect
import json
import re
import secrets
from collections import Counter
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from ..capabilities import (
    CapabilityEffect,
    CapabilityError,
    CapabilityExecutor,
    CapabilityExposure,
    CapabilityRegistry,
    CapabilityResult,
    ExecutionAuthority,
    JsonValue,
)
from .service import PlannedCapability


class CapabilityPlanError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class CapabilityPlanStepError(CapabilityPlanError):
    """Sanitized failure bound to the plan step that the host was executing."""

    def __init__(self, code, *, step_id, capability, phase, details=None):
        super().__init__(code)
        self.step_id = step_id
        self.capability = capability
        self.phase = phase
        self.details = dict(details or {})


@dataclass(frozen=True, slots=True)
class CapabilityPlanExecution:
    payload: dict[str, JsonValue]
    results: tuple[CapabilityResult, ...]


BeforeEffect = Callable[[], None | Awaitable[None]]
RecoveryCheckpoint = Callable[
    [str, dict[str, JsonValue], dict[str, JsonValue], bool],
    None | Awaitable[None],
]
_SEMANTIC_GROUP_RE = re.compile(r"^semantic:v1:[0-9a-f]{32}$")
_MAX_EFFECT_STEPS = 5
_RECOVERY_MODES = frozenset({"odoo_atomic", "segmented", "external"})
_JOURNAL_CLASSES = frozenset(
    {"none", "reversible", "reconstructable", "irreversible", "external_or_unknown"}
)
_TERMINAL_STEP_STATES = frozenset({"completed", "skipped"})
_INCOMPLETE_DEPENDENCY_OUTCOMES = frozenset({"partial", "blocked"})
_DEPENDENCY_OUTCOME_SEMANTICS = "continue_on_error"


class CapabilityPlanService:
    """Prepare/execute typed effect steps without knowing business capability names."""

    def __init__(self, *, registry: CapabilityRegistry, executor: CapabilityExecutor) -> None:
        self._registry = registry
        self._executor = executor

    async def prepare(
        self,
        plan: tuple[PlannedCapability, ...],
    ) -> dict[str, JsonValue]:
        if not isinstance(plan, tuple) or not 1 <= len(plan) <= _MAX_EFFECT_STEPS:
            raise CapabilityPlanError("capability_plan_invalid")
        _validate_requested_dependencies(plan)
        steps: list[dict[str, JsonValue]] = []
        requires_confirmation = False
        for position, requested in enumerate(plan):
            definition = self._registry.resolve(requested.capability)
            semantic_groups = {
                "prepare": _new_semantic_group_key(),
                "execute": _new_semantic_group_key(),
                "verify": _new_semantic_group_key(),
            }
            try:
                preview = await self._executor.preview(
                    definition.name,
                    requested.arguments,
                    semantic_group_key=semantic_groups["prepare"],
                )
            except CapabilityError as error:
                raise CapabilityPlanStepError(
                    error.code,
                    step_id=requested.step_id or f"step-{position + 1}",
                    capability=definition.name,
                    phase="prepare",
                    details=error.details,
                ) from error
            approval_required = self._executor.approval_required(definition.name)
            requires_confirmation = requires_confirmation or approval_required
            steps.append(
                {
                    "position": position,
                    "step_id": requested.step_id or f"step-{position + 1}",
                    "depends_on": list(requested.depends_on),
                    "capability": definition.name,
                    "version": definition.version,
                    "arguments": dict(requested.arguments),
                    "title": requested.summary,
                    "risk": _risk(definition.risk.value, definition.effect.value),
                    "effect": _effect(definition.effect.value),
                    "approval": definition.approval.value,
                    "approval_required": approval_required,
                    "precondition_fingerprint": preview.precondition_fingerprint,
                    "binding_fingerprint": _binding_fingerprint(
                        definition.name,
                        definition.version,
                        requested.arguments,
                        preview.precondition_fingerprint,
                    ),
                    "preview": dict(preview.summary),
                    "state": "previewed",
                    "result": None,
                    "verification": None,
                    "semantic_groups": semantic_groups,
                    "recovery_unit_id": "",
                    "recovery_mode": _recovery_mode(definition),
                    "journal_classification": _journal_classification(
                        self._registry,
                        definition,
                        preview=dict(preview.summary),
                    ),
                }
            )
        recovery_units = _assign_recovery_units(steps)
        return {
            "format_version": 3,
            "state": "awaiting_confirmation" if requires_confirmation else "authorized",
            "requires_confirmation": requires_confirmation,
            "recovery_units": recovery_units,
            "steps": steps,
        }

    async def execute(
        self,
        payload: dict[str, JsonValue],
        *,
        human_approved: bool,
        before_effect: BeforeEffect | None = None,
        recovery_checkpoint: RecoveryCheckpoint | None = None,
    ) -> CapabilityPlanExecution:
        """Execute recovery units without pretending external effects are database-atomic.

        Consecutive Odoo-local atomic steps share one transaction/recovery unit. Segmented or
        external steps require a host checkpoint callback so completed units and an in-flight
        external unit are durably distinguishable. The final unit remains in the caller's current
        transaction so its verified receipt can be persisted with the final business state.
        """

        source_version = payload.get("format_version") if isinstance(payload, dict) else None
        plan = _validated_plan(payload)
        if source_version in {1, 2}:
            plan = _upgrade_legacy_recovery(self._registry, plan)
        if plan["state"] not in {"authorized", "executing"}:
            raise CapabilityPlanError("capability_plan_not_authorized")
        recovery_units = [dict(item) for item in plan["recovery_units"]]
        if any(unit["state"] == "executing" for unit in recovery_units):
            raise CapabilityPlanError("capability_plan_recovery_required")
        if (
            recovery_checkpoint is None
            and (
                len(recovery_units) > 1
                or any(unit["mode"] != "odoo_atomic" for unit in recovery_units)
            )
        ):
            raise CapabilityPlanError("capability_plan_recovery_checkpoint_required")

        steps = [dict(item) for item in plan["steps"]]
        outcome_contracts = _step_outcome_contracts(self._registry, steps)
        _validate_skipped_dependency_evidence(steps, outcome_contracts)
        _validate_execution_call_budget(
            self._registry,
            steps,
            outcome_contracts=outcome_contracts,
        )
        results: list[CapabilityResult] = []
        terminal_ids = {
            step["step_id"]
            for step in steps
            if step.get("state") in _TERMINAL_STEP_STATES
        }
        satisfied_ids = {
            step["step_id"]
            for step in steps
            if _step_satisfies_dependencies(step, outcome_contracts)
        }
        barrier_crossed = False

        for unit_index, raw_unit in enumerate(recovery_units):
            if raw_unit["state"] == "completed":
                continue
            if raw_unit["state"] != "prepared":
                raise CapabilityPlanError("capability_plan_recovery_required")
            unit = dict(raw_unit)
            definitions = await self._preflight_unit(
                unit,
                steps=steps,
                terminal_ids=terminal_ids,
                satisfied_ids=satisfied_ids,
                human_approved=human_approved,
            )
            unit["state"] = "executing"
            recovery_units[unit_index] = unit
            plan_snapshot = _execution_snapshot(
                plan,
                steps=steps,
                recovery_units=recovery_units,
                state="executing",
            )
            is_last_unit = unit_index == len(recovery_units) - 1

            if recovery_checkpoint is not None:
                pending = recovery_checkpoint(
                    "before_unit",
                    plan_snapshot,
                    dict(unit),
                    is_last_unit,
                )
                if inspect.isawaitable(pending):
                    await pending
                barrier_crossed = True
            elif not barrier_crossed and before_effect is not None:
                pending = before_effect()
                if inspect.isawaitable(pending):
                    await pending
                barrier_crossed = True

            for step_id in unit["step_ids"]:
                index = _step_index(steps, step_id)
                step = dict(steps[index])
                if step["state"] in _TERMINAL_STEP_STATES:
                    terminal_ids.add(step_id)
                    if _step_satisfies_dependencies(step, outcome_contracts):
                        satisfied_ids.add(step_id)
                    continue
                depends_on = tuple(step["depends_on"])
                if any(dependency not in satisfied_ids for dependency in depends_on):
                    result, verification = _dependency_skip_evidence(
                        step,
                        steps,
                        outcome_contracts,
                    )
                    step["state"] = "skipped"
                    step["result"] = result
                    step["verification"] = verification
                    steps[index] = step
                    terminal_ids.add(step_id)
                    continue
                definition = definitions[step_id]
                step["state"] = "executing"
                steps[index] = step
                try:
                    result = await self._executor.execute(
                        definition.name,
                        step["arguments"],
                        authority=ExecutionAuthority.PLAN,
                        approved=human_approved,
                        semantic_group_key=step["semantic_groups"]["execute"],
                    )
                    verification = await self._executor.verify(
                        definition.name,
                        step["arguments"],
                        result,
                        semantic_group_key=step["semantic_groups"]["verify"],
                    )
                except CapabilityError as error:
                    raise CapabilityPlanStepError(
                        error.code,
                        step_id=step_id,
                        capability=definition.name,
                        phase="execution",
                        details=error.details,
                    ) from error
                if verification.verified is not True:
                    raise CapabilityPlanStepError(
                        "capability_plan_verification_failed",
                        step_id=step_id,
                        capability=definition.name,
                        phase="execution",
                    )
                step["state"] = "completed"
                step["result"] = dict(result.data)
                step["verification"] = dict(verification.summary)
                steps[index] = step
                results.append(result)
                terminal_ids.add(step_id)
                if _step_satisfies_dependencies(step, outcome_contracts):
                    satisfied_ids.add(step_id)

            unit["state"] = "completed"
            recovery_units[unit_index] = unit
            plan_snapshot = _execution_snapshot(
                plan,
                steps=steps,
                recovery_units=recovery_units,
                state="completed" if is_last_unit else "executing",
            )
            if recovery_checkpoint is not None and not is_last_unit:
                pending = recovery_checkpoint(
                    "after_unit",
                    plan_snapshot,
                    dict(unit),
                    False,
                )
                if inspect.isawaitable(pending):
                    await pending

        completed = _execution_snapshot(
            plan,
            steps=steps,
            recovery_units=recovery_units,
            state="completed",
        )
        return CapabilityPlanExecution(payload=completed, results=tuple(results))

    def approval_refines(self, approved, candidate):
        """Return true when a repaired plan cannot exceed the user's approved effect scope."""

        original = _validated_plan(approved)
        repaired = _validated_plan(candidate)
        original_scopes = _approval_scopes(self._registry, original["steps"])
        repaired_scopes = _approval_scopes(self._registry, repaired["steps"])
        return all(
            key in original_scopes and values <= original_scopes[key]
            for key, values in repaired_scopes.items()
        ) and bool(repaired_scopes)

    async def _preflight_unit(
        self,
        unit,
        *,
        steps,
        terminal_ids,
        satisfied_ids,
        human_approved,
    ):
        unit_ids = list(unit["step_ids"])
        unit_seen: set[str] = set()
        known_unsatisfied = set(terminal_ids) - set(satisfied_ids)
        definitions = {}
        for step_id in unit_ids:
            index = _step_index(steps, step_id)
            step = steps[index]
            if step["state"] in _TERMINAL_STEP_STATES:
                unit_seen.add(step_id)
                continue
            if step["state"] not in {"previewed", "executing"}:
                raise CapabilityPlanError("capability_plan_invalid")
            if any(
                dependency not in terminal_ids and dependency not in unit_seen
                for dependency in step["depends_on"]
            ):
                raise CapabilityPlanError("capability_plan_dependency_unsatisfied")
            if any(dependency in known_unsatisfied for dependency in step["depends_on"]):
                known_unsatisfied.add(step_id)
                unit_seen.add(step_id)
                continue
            definition = self._registry.resolve(step["capability"])
            if definition.version != step["version"]:
                raise CapabilityPlanError("capability_plan_version_mismatch")
            if _recovery_mode(definition) != step["recovery_mode"]:
                raise CapabilityPlanError("capability_plan_recovery_binding_mismatch")
            expected_binding = _binding_fingerprint(
                definition.name,
                definition.version,
                step["arguments"],
                step["precondition_fingerprint"],
            )
            if expected_binding != step["binding_fingerprint"]:
                raise CapabilityPlanError("capability_plan_binding_mismatch")
            try:
                current_preview = await self._executor.preview(
                    definition.name,
                    step["arguments"],
                    semantic_group_key=step["semantic_groups"]["prepare"],
                )
            except CapabilityError as error:
                raise CapabilityPlanStepError(
                    error.code,
                    step_id=step_id,
                    capability=definition.name,
                    phase="preflight",
                    details=error.details,
                ) from error
            if current_preview.precondition_fingerprint != step["precondition_fingerprint"]:
                raise CapabilityPlanStepError(
                    "capability_plan_precondition_changed",
                    step_id=step_id,
                    capability=definition.name,
                    phase="preflight",
                )
            if (
                _journal_classification(
                    self._registry,
                    definition,
                    preview=dict(current_preview.summary),
                )
                != step["journal_classification"]
            ):
                raise CapabilityPlanError("capability_plan_journal_binding_mismatch")
            if self._executor.approval_required(
                definition.name,
                approved=human_approved,
            ):
                raise CapabilityPlanError("capability_plan_approval_required")
            definitions[step_id] = definition
            unit_seen.add(step_id)
        return definitions


def _validate_execution_call_budget(registry, steps, *, outcome_contracts):
    """Reject an internally impossible plan before crossing the write barrier."""

    pending = Counter(
        step["capability"]
        for step in _potentially_executable_steps(steps, outcome_contracts)
    )
    for capability, count in pending.items():
        definition = registry.resolve(capability)
        if count > definition.max_calls:
            raise CapabilityPlanError("capability_call_limit_exceeded")


def _step_outcome_contracts(registry, steps):
    """Bind dependency semantics to trusted capability metadata, never result field names alone."""

    contracts = {}
    for step in steps:
        definition = registry.resolve(step["capability"])
        if definition.version != step["version"]:
            raise CapabilityPlanError("capability_plan_version_mismatch")
        semantics = definition.developer_metadata.get("partial_failure_semantics")
        contracts[step["step_id"]] = semantics == _DEPENDENCY_OUTCOME_SEMANTICS
    return contracts


def _step_satisfies_dependencies(step, outcome_contracts):
    if step.get("state") != "completed":
        return False
    if outcome_contracts.get(step.get("step_id")) is not True:
        return True
    result = step.get("result")
    return not (
        isinstance(result, dict)
        and result.get("outcome") in _INCOMPLETE_DEPENDENCY_OUTCOMES
    )


def _potentially_executable_steps(steps, outcome_contracts):
    """Exclude only steps already proven impossible by a terminal dependency outcome."""

    blocked_ids = set()
    executable = []
    for step in steps:
        step_id = step["step_id"]
        if step.get("state") in _TERMINAL_STEP_STATES:
            if not _step_satisfies_dependencies(step, outcome_contracts):
                blocked_ids.add(step_id)
            continue
        if any(dependency in blocked_ids for dependency in step["depends_on"]):
            blocked_ids.add(step_id)
            continue
        executable.append(step)
    return executable


def _dependency_skip_evidence(step, steps, outcome_contracts):
    by_id = {item["step_id"]: item for item in steps}
    dependencies = []
    for dependency_id in step["depends_on"]:
        dependency = by_id.get(dependency_id)
        outcome = _unsatisfied_dependency_outcome(dependency, outcome_contracts)
        if outcome is not None:
            dependencies.append({"step_id": dependency_id, "outcome": outcome})
    if not dependencies:
        raise CapabilityPlanError("capability_plan_dependency_unsatisfied")
    result = {
        "outcome": "skipped",
        "reason": "dependency_incomplete",
        "executed": False,
        "dependencies": dependencies,
    }
    verification = {"verified": True, **result}
    return result, verification


def _unsatisfied_dependency_outcome(step, outcome_contracts):
    if not isinstance(step, dict):
        return None
    if step.get("state") == "skipped":
        return "skipped"
    if (
        step.get("state") == "completed"
        and outcome_contracts.get(step.get("step_id")) is True
        and isinstance(step.get("result"), dict)
        and step["result"].get("outcome") in _INCOMPLETE_DEPENDENCY_OUTCOMES
    ):
        return step["result"]["outcome"]
    return None


def _validate_skipped_dependency_evidence(steps, outcome_contracts):
    for step in steps:
        if step.get("state") != "skipped":
            continue
        expected_result, expected_verification = _dependency_skip_evidence(
            step,
            steps,
            outcome_contracts,
        )
        if (
            step.get("result") != expected_result
            or step.get("verification") != expected_verification
        ):
            raise CapabilityPlanError("capability_plan_invalid")


def _approval_scopes(registry, steps):
    scopes = {}
    exact = Counter()
    for step in steps:
        definition = registry.resolve(step["capability"])
        arguments = step["arguments"]
        mode = definition.developer_metadata.get("approval_refinement")
        if mode == "record_id_subset":
            model = arguments.get("model")
            operation = arguments.get("operation")
            record_ids = arguments.get("record_ids")
            if (
                not isinstance(model, str)
                or not isinstance(operation, str)
                or not isinstance(record_ids, list)
                or any(type(record_id) is not int for record_id in record_ids)
            ):
                raise CapabilityPlanError("capability_plan_invalid")
            key = (definition.name, model, operation)
            scopes.setdefault(key, set()).update(record_ids)
            continue
        exact[(definition.name, _canonical_arguments(arguments))] += 1
    for key, count in exact.items():
        scopes[("exact", *key)] = set(range(count))
    return scopes


def _canonical_arguments(arguments):
    try:
        return json.dumps(
            arguments,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError):
        raise CapabilityPlanError("capability_plan_invalid") from None


def _validated_plan(payload):
    if not isinstance(payload, dict):
        raise CapabilityPlanError("capability_plan_invalid")
    version = payload.get("format_version")
    if version not in {1, 2, 3} or type(payload.get("requires_confirmation")) is not bool:
        raise CapabilityPlanError("capability_plan_invalid")
    expected_root = (
        {"format_version", "state", "requires_confirmation", "steps"}
        if version in {1, 2}
        else {
            "format_version",
            "state",
            "requires_confirmation",
            "recovery_units",
            "steps",
        }
    )
    if set(payload) != expected_root:
        raise CapabilityPlanError("capability_plan_invalid")
    if payload.get("state") not in {
        "awaiting_confirmation",
        "authorized",
        "executing",
        "completed",
        "rejected",
    }:
        raise CapabilityPlanError("capability_plan_invalid")
    raw_steps = payload.get("steps")
    if not isinstance(raw_steps, list) or not 1 <= len(raw_steps) <= _MAX_EFFECT_STEPS:
        raise CapabilityPlanError("capability_plan_invalid")

    normalized_steps = []
    known_ids: set[str] = set()
    previous_id: str | None = None
    for position, raw_step in enumerate(raw_steps):
        if not isinstance(raw_step, dict):
            raise CapabilityPlanError("capability_plan_invalid")
        step = dict(raw_step)
        if version == 1:
            expected = {
                "position",
                "capability",
                "version",
                "arguments",
                "title",
                "risk",
                "effect",
                "approval",
                "approval_required",
                "precondition_fingerprint",
                "binding_fingerprint",
                "preview",
                "state",
                "result",
                "verification",
                "semantic_groups",
            }
            if set(step) != expected:
                raise CapabilityPlanError("capability_plan_invalid")
            step_id = f"step-{position + 1}"
            step["step_id"] = step_id
            step["depends_on"] = [previous_id] if previous_id is not None else []
        elif version == 2:
            expected = {
                "position",
                "step_id",
                "depends_on",
                "capability",
                "version",
                "arguments",
                "title",
                "risk",
                "effect",
                "approval",
                "approval_required",
                "precondition_fingerprint",
                "binding_fingerprint",
                "preview",
                "state",
                "result",
                "verification",
                "semantic_groups",
            }
            if set(step) != expected:
                raise CapabilityPlanError("capability_plan_invalid")
            step_id = step.get("step_id")
        else:
            expected = {
                "position",
                "step_id",
                "depends_on",
                "capability",
                "version",
                "arguments",
                "title",
                "risk",
                "effect",
                "approval",
                "approval_required",
                "precondition_fingerprint",
                "binding_fingerprint",
                "preview",
                "state",
                "result",
                "verification",
                "semantic_groups",
                "recovery_unit_id",
                "recovery_mode",
                "journal_classification",
            }
            if set(step) != expected:
                raise CapabilityPlanError("capability_plan_invalid")
            step_id = step.get("step_id")

        semantic_groups = step.get("semantic_groups")
        depends_on = step.get("depends_on")
        if (
            not isinstance(step_id, str)
            or not 1 <= len(step_id) <= 256
            or step_id in known_ids
            or not isinstance(depends_on, list)
            or len(set(depends_on)) != len(depends_on)
            or any(not isinstance(item, str) or item not in known_ids for item in depends_on)
            or not isinstance(semantic_groups, dict)
            or set(semantic_groups) != {"prepare", "execute", "verify"}
            or any(
                not isinstance(value, str) or _SEMANTIC_GROUP_RE.fullmatch(value) is None
                for value in semantic_groups.values()
            )
            or len(set(semantic_groups.values())) != 3
        ):
            raise CapabilityPlanError("capability_plan_invalid")
        if (
            step.get("position") != position
            or not isinstance(step.get("capability"), str)
            or not isinstance(step.get("version"), str)
            or not isinstance(step.get("arguments"), dict)
            or not isinstance(step.get("title"), str)
            or step.get("approval") not in {"none", "policy", "always"}
            or type(step.get("approval_required")) is not bool
            or not isinstance(step.get("preview"), dict)
            or step.get("state")
            not in {"previewed", "executing", "completed", "skipped"}
        ):
            raise CapabilityPlanError("capability_plan_invalid")
        if version in {1, 2}:
            step["recovery_unit_id"] = "unit-1"
            step["recovery_mode"] = "odoo_atomic"
            step["journal_classification"] = "external_or_unknown"
        elif (
            not isinstance(step.get("recovery_unit_id"), str)
            or not step["recovery_unit_id"]
            or step.get("recovery_mode") not in _RECOVERY_MODES
            or step.get("journal_classification") not in _JOURNAL_CLASSES
        ):
            raise CapabilityPlanError("capability_plan_invalid")
        known_ids.add(step_id)
        previous_id = step_id
        normalized_steps.append(step)

    if version in {1, 2}:
        recovery_units = [
            {
                "unit_id": "unit-1",
                "mode": "odoo_atomic",
                "step_ids": [step["step_id"] for step in normalized_steps],
                "state": (
                    "completed"
                    if all(step["state"] == "completed" for step in normalized_steps)
                    else "prepared"
                ),
            }
        ]
    else:
        raw_units = payload.get("recovery_units")
        recovery_units = _validated_recovery_units(raw_units, normalized_steps)

    normalized = dict(payload)
    normalized["format_version"] = 3
    normalized["recovery_units"] = recovery_units
    normalized["steps"] = normalized_steps
    return normalized


def _upgrade_legacy_recovery(registry, plan):
    steps = [dict(step) for step in plan["steps"]]
    for step in steps:
        definition = registry.resolve(step["capability"])
        if definition.version != step["version"]:
            raise CapabilityPlanError("capability_plan_version_mismatch")
        step["recovery_mode"] = _recovery_mode(definition)
        step["journal_classification"] = _journal_classification(registry, definition)
        step["recovery_unit_id"] = ""
    recovery_units = _assign_recovery_units(steps)
    return _execution_snapshot(
        plan,
        steps=steps,
        recovery_units=recovery_units,
        state=plan["state"],
    )


def _validated_recovery_units(raw_units, steps):
    if not isinstance(raw_units, list) or not 1 <= len(raw_units) <= len(steps):
        raise CapabilityPlanError("capability_plan_invalid")
    step_by_id = {step["step_id"]: step for step in steps}
    seen_steps: set[str] = set()
    normalized = []
    for index, raw in enumerate(raw_units):
        if not isinstance(raw, dict) or set(raw) != {"unit_id", "mode", "step_ids", "state"}:
            raise CapabilityPlanError("capability_plan_invalid")
        unit = dict(raw)
        unit_id = unit.get("unit_id")
        mode = unit.get("mode")
        step_ids = unit.get("step_ids")
        if (
            unit_id != f"unit-{index + 1}"
            or mode not in _RECOVERY_MODES
            or unit.get("state") not in {"prepared", "executing", "completed"}
            or not isinstance(step_ids, list)
            or not step_ids
            or len(step_ids) != len(set(step_ids))
        ):
            raise CapabilityPlanError("capability_plan_invalid")
        for step_id in step_ids:
            step = step_by_id.get(step_id)
            if (
                step is None
                or step_id in seen_steps
                or step.get("recovery_unit_id") != unit_id
                or step.get("recovery_mode") != mode
            ):
                raise CapabilityPlanError("capability_plan_invalid")
            seen_steps.add(step_id)
        if mode != "odoo_atomic" and len(step_ids) != 1:
            raise CapabilityPlanError("capability_plan_invalid")
        normalized.append(unit)
    if seen_steps != set(step_by_id):
        raise CapabilityPlanError("capability_plan_invalid")
    flattened = [step_id for unit in normalized for step_id in unit["step_ids"]]
    if flattened != [step["step_id"] for step in steps]:
        raise CapabilityPlanError("capability_plan_invalid")
    return normalized


def _assign_recovery_units(steps):
    units: list[dict[str, JsonValue]] = []
    for step in steps:
        mode = step["recovery_mode"]
        if mode == "odoo_atomic" and units and units[-1]["mode"] == "odoo_atomic":
            unit = units[-1]
        else:
            unit = {
                "unit_id": f"unit-{len(units) + 1}",
                "mode": mode,
                "step_ids": [],
                "state": "prepared",
            }
            units.append(unit)
        unit["step_ids"].append(step["step_id"])
        step["recovery_unit_id"] = unit["unit_id"]
    return units


def _execution_snapshot(plan, *, steps, recovery_units, state):
    snapshot = dict(plan)
    snapshot["format_version"] = 3
    snapshot["state"] = state
    snapshot["steps"] = [dict(step) for step in steps]
    snapshot["recovery_units"] = [dict(unit) for unit in recovery_units]
    return snapshot


def _step_index(steps, step_id):
    for index, step in enumerate(steps):
        if step.get("step_id") == step_id:
            return index
    raise CapabilityPlanError("capability_plan_invalid")


def _recovery_mode(definition):
    explicit = definition.audit_metadata.get("recovery_mode")
    if explicit is not None:
        if explicit not in _RECOVERY_MODES:
            raise CapabilityPlanError("capability_recovery_metadata_invalid")
        return explicit
    if definition.effect in {
        CapabilityEffect.INTERNAL_REVERSIBLE,
        CapabilityEffect.INTERNAL_IRREVERSIBLE,
        CapabilityEffect.READ_ONLY,
    }:
        return "odoo_atomic"
    return "external"


def _journal_classification(registry, definition, *, preview=None):
    explicit = definition.audit_metadata.get("journal_classification")
    if explicit is not None:
        if explicit not in _JOURNAL_CLASSES:
            raise CapabilityPlanError("capability_journal_metadata_invalid")
        if explicit == "reversible" and definition.effect is not CapabilityEffect.INTERNAL_REVERSIBLE:
            raise CapabilityPlanError("capability_journal_metadata_invalid")
        if explicit == "reconstructable" and preview is not None:
            reconstruction = preview.get("reconstruction") if isinstance(preview, dict) else None
            if (
                not isinstance(reconstruction, dict)
                or reconstruction.get("required_complete") is not True
                or not isinstance(reconstruction.get("values"), dict)
                or not reconstruction["values"]
            ):
                return "irreversible"
        return explicit
    if definition.effect is CapabilityEffect.READ_ONLY:
        return "none"
    if definition.effect in {CapabilityEffect.EXTERNAL, CapabilityEffect.HOST}:
        return "external_or_unknown"
    if definition.effect is CapabilityEffect.INTERNAL_REVERSIBLE:
        try:
            compensation = registry.resolve(f"{definition.name}.revert")
        except Exception:  # noqa: BLE001 - absence means no structural reversible claim
            compensation = None
        if (
            compensation is not None
            and compensation.exposure is CapabilityExposure.HOST
            and compensation.effect is CapabilityEffect.INTERNAL_REVERSIBLE
        ):
            return "reversible"
        if "create" in definition.tags:
            return "reconstructable"
    return "irreversible"


def _validate_requested_dependencies(plan: tuple[PlannedCapability, ...]) -> None:
    known: set[str] = set()
    for position, step in enumerate(plan):
        step_id = step.step_id or f"step-{position + 1}"
        if step_id in known or any(dep not in known for dep in step.depends_on):
            raise CapabilityPlanError("capability_plan_dependency_invalid")
        known.add(step_id)


def _new_semantic_group_key():
    return f"semantic:v1:{secrets.token_hex(16)}"


def _binding_fingerprint(name, version, arguments, precondition):
    body = json.dumps(
        {
            "name": name,
            "version": version,
            "arguments": arguments,
            "precondition": precondition,
        },
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(body).hexdigest()}"


def _risk(risk, effect):
    if effect in {"internal-irreversible", "external", "host"} or risk == "host":
        return "protected"
    if risk == "action":
        return "high"
    if risk in {"write", "action-preview"}:
        return "moderate"
    return "low"


def _effect(effect):
    return {
        "read-only": "read_only",
        "internal-reversible": "internal_reversible",
        "internal-irreversible": "internal_irreversible",
        "external": "external",
        "host": "external",
    }[effect]
