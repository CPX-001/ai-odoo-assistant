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
            preview = await self._executor.preview(
                definition.name,
                requested.arguments,
                semantic_group_key=semantic_groups["prepare"],
            )
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
        _validate_execution_call_budget(self._registry, steps)
        results: list[CapabilityResult] = []
        completed_ids = {
            step["step_id"] for step in steps if step.get("state") == "completed"
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
                completed_ids=completed_ids,
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
                if step["state"] == "completed":
                    completed_ids.add(step_id)
                    continue
                depends_on = tuple(step["depends_on"])
                if any(dependency not in completed_ids for dependency in depends_on):
                    raise CapabilityPlanError("capability_plan_dependency_unsatisfied")
                definition = definitions[step_id]
                step["state"] = "executing"
                steps[index] = step
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
                if verification.verified is not True:
                    raise CapabilityPlanError("capability_plan_verification_failed")
                step["state"] = "completed"
                step["result"] = dict(result.data)
                step["verification"] = dict(verification.summary)
                steps[index] = step
                results.append(result)
                completed_ids.add(step_id)

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

    async def _preflight_unit(
        self,
        unit,
        *,
        steps,
        completed_ids,
        human_approved,
    ):
        unit_ids = list(unit["step_ids"])
        unit_seen: set[str] = set()
        definitions = {}
        for step_id in unit_ids:
            index = _step_index(steps, step_id)
            step = steps[index]
            if step["state"] == "completed":
                unit_seen.add(step_id)
                continue
            if step["state"] not in {"previewed", "executing"}:
                raise CapabilityPlanError("capability_plan_invalid")
            if any(
                dependency not in completed_ids and dependency not in unit_seen
                for dependency in step["depends_on"]
            ):
                raise CapabilityPlanError("capability_plan_dependency_unsatisfied")
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
            current_preview = await self._executor.preview(
                definition.name,
                step["arguments"],
                semantic_group_key=step["semantic_groups"]["prepare"],
            )
            if current_preview.precondition_fingerprint != step["precondition_fingerprint"]:
                raise CapabilityPlanError("capability_plan_precondition_changed")
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


def _validate_execution_call_budget(registry, steps):
    """Reject an internally impossible plan before crossing the write barrier."""

    pending = Counter(
        step["capability"] for step in steps if step.get("state") != "completed"
    )
    for capability, count in pending.items():
        definition = registry.resolve(capability)
        if count > definition.max_calls:
            raise CapabilityPlanError("capability_call_limit_exceeded")


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
            or step.get("state") not in {"previewed", "executing", "completed"}
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
