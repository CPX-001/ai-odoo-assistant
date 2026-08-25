"""Provider-neutral preparation and execution of capability plans."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from ..capabilities import (
    CapabilityError,
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


class CapabilityPlanService:
    """Prepare/execute plan capabilities without knowing any capability name."""

    def __init__(self, *, registry: CapabilityRegistry, executor: CapabilityExecutor) -> None:
        self._registry = registry
        self._executor = executor

    async def prepare(
        self,
        plan: tuple[PlannedCapability, ...],
    ) -> dict[str, JsonValue]:
        steps: list[dict[str, JsonValue]] = []
        requires_confirmation = False
        for position, requested in enumerate(plan):
            definition = self._registry.resolve(requested.capability)
            preview = await self._executor.preview(
                definition.name,
                requested.arguments,
            )
            approval_required = self._executor.approval_required(definition.name)
            requires_confirmation = requires_confirmation or approval_required
            steps.append(
                {
                    "position": position,
                    "capability": definition.name,
                    "version": definition.version,
                    "arguments": dict(requested.arguments),
                    "title": requested.summary,
                    "risk": _risk(definition.risk.value, definition.effect.value),
                    "effect": _effect(definition.effect.value),
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
                }
            )
        return {
            "format_version": 1,
            "state": "awaiting_confirmation" if requires_confirmation else "authorized",
            "requires_confirmation": requires_confirmation,
            "steps": steps,
        }

    async def execute(
        self,
        payload: dict[str, JsonValue],
        *,
        human_approved: bool,
    ) -> CapabilityPlanExecution:
        plan = _validated_plan(payload)
        if plan["state"] not in {"authorized", "executing"}:
            raise CapabilityPlanError("capability_plan_not_authorized")
        steps = list(plan["steps"])
        results: list[CapabilityResult] = []
        for index, raw_step in enumerate(steps):
            step = dict(raw_step)
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
            )
            if current_preview.precondition_fingerprint != step["precondition_fingerprint"]:
                raise CapabilityPlanError("capability_plan_precondition_changed")
            step["state"] = "executing"
            steps[index] = step
            result = await self._executor.execute(
                definition.name,
                step["arguments"],
                authority=ExecutionAuthority.PLAN,
                approved=human_approved or not bool(step["approval_required"]),
            )
            verification = await self._executor.verify(
                definition.name,
                step["arguments"],
                result,
            )
            step["state"] = "completed"
            step["result"] = dict(result.data)
            step["verification"] = dict(verification.summary)
            steps[index] = step
            results.append(result)
        completed = dict(plan)
        completed["state"] = "completed"
        completed["steps"] = steps
        return CapabilityPlanExecution(payload=completed, results=tuple(results))


def _validated_plan(payload):
    if not isinstance(payload, dict):
        raise CapabilityPlanError("capability_plan_invalid")
    if set(payload) != {"format_version", "state", "requires_confirmation", "steps"}:
        raise CapabilityPlanError("capability_plan_invalid")
    if payload.get("format_version") != 1 or type(payload.get("requires_confirmation")) is not bool:
        raise CapabilityPlanError("capability_plan_invalid")
    steps = payload.get("steps")
    if not isinstance(steps, list) or not 1 <= len(steps) <= 12:
        raise CapabilityPlanError("capability_plan_invalid")
    for position, step in enumerate(steps):
        if not isinstance(step, dict) or set(step) != {
            "position",
            "capability",
            "version",
            "arguments",
            "title",
            "risk",
            "effect",
            "approval_required",
            "precondition_fingerprint",
            "binding_fingerprint",
            "preview",
            "state",
            "result",
            "verification",
        }:
            raise CapabilityPlanError("capability_plan_invalid")
        if (
            step.get("position") != position
            or not isinstance(step.get("capability"), str)
            or not isinstance(step.get("version"), str)
            or not isinstance(step.get("arguments"), dict)
            or not isinstance(step.get("title"), str)
            or type(step.get("approval_required")) is not bool
            or not isinstance(step.get("preview"), dict)
            or step.get("state") not in {"previewed", "executing", "completed"}
        ):
            raise CapabilityPlanError("capability_plan_invalid")
    return payload


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
