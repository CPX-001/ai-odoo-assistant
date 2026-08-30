"""Provider-neutral preparation and execution of capability EffectPlans."""

from __future__ import annotations

import hashlib
import inspect
import json
import re
import secrets
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from ..capabilities import (
    CapabilityExecutor,
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
_SEMANTIC_GROUP_RE = re.compile(r"^semantic:v1:[0-9a-f]{32}$")
_MAX_EFFECT_STEPS = 5


class CapabilityPlanService:
    """Prepare/execute typed effect steps without knowing any capability name."""

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
                }
            )
        return {
            "format_version": 2,
            "state": "awaiting_confirmation" if requires_confirmation else "authorized",
            "requires_confirmation": requires_confirmation,
            "steps": steps,
        }

    async def execute(
        self,
        payload: dict[str, JsonValue],
        *,
        human_approved: bool,
        before_effect: BeforeEffect | None = None,
    ) -> CapabilityPlanExecution:
        """Revalidate each typed step and cross one Odoo-local barrier before effects.

        Phase 6.3 keeps the current Odoo-local transaction semantics: all supported steps execute
        in order inside the same business transaction after one durable barrier. Segmented/external
        recovery units are deliberately left to P6.4 rather than pretending they are atomic.
        """

        plan = _validated_plan(payload)
        if plan["state"] not in {"authorized", "executing"}:
            raise CapabilityPlanError("capability_plan_not_authorized")
        steps = list(plan["steps"])
        results: list[CapabilityResult] = []
        completed_ids: set[str] = set()
        barrier_crossed = False
        for index, raw_step in enumerate(steps):
            step = dict(raw_step)
            step_id = step["step_id"]
            depends_on = tuple(step["depends_on"])
            if any(dependency not in completed_ids for dependency in depends_on):
                raise CapabilityPlanError("capability_plan_dependency_unsatisfied")
            definition = self._registry.resolve(step["capability"])
            if definition.version != step["version"]:
                raise CapabilityPlanError("capability_plan_version_mismatch")
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
            if self._executor.approval_required(
                definition.name,
                approved=human_approved,
            ):
                raise CapabilityPlanError("capability_plan_approval_required")
            step["state"] = "executing"
            steps[index] = step
            if not barrier_crossed and before_effect is not None:
                pending = before_effect()
                if inspect.isawaitable(pending):
                    await pending
                barrier_crossed = True
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
            step["state"] = "completed"
            step["result"] = dict(result.data)
            step["verification"] = dict(verification.summary)
            steps[index] = step
            results.append(result)
            completed_ids.add(step_id)
        completed = dict(plan)
        completed["state"] = "completed"
        completed["steps"] = steps
        return CapabilityPlanExecution(payload=completed, results=tuple(results))


def _validated_plan(payload):
    if not isinstance(payload, dict):
        raise CapabilityPlanError("capability_plan_invalid")
    if set(payload) != {"format_version", "state", "requires_confirmation", "steps"}:
        raise CapabilityPlanError("capability_plan_invalid")
    version = payload.get("format_version")
    if version not in {1, 2} or type(payload.get("requires_confirmation")) is not bool:
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
        known_ids.add(step_id)
        previous_id = step_id
        normalized_steps.append(step)
    normalized = dict(payload)
    normalized["format_version"] = 2
    normalized["steps"] = normalized_steps
    return normalized


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
