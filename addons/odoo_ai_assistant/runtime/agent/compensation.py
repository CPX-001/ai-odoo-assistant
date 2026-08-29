"""Host-owned compensating actions for already verified Assistant effects."""

from __future__ import annotations

from dataclasses import dataclass

from ..capabilities import (
    CapabilityContext,
    CapabilityEffect,
    CapabilityError,
    CapabilityExecutor,
    CapabilityExposure,
    CapabilityRegistry,
    CapabilityResult,
    ExecutionAuthority,
)


class CapabilityCompensationError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class CapabilityCompensationExecution:
    results: tuple[CapabilityResult, ...]


def compensation_capability_name(capability: str) -> str:
    if not isinstance(capability, str) or not capability:
        raise CapabilityCompensationError("capability_compensation_invalid")
    return f"{capability}.revert"


def plan_is_compensatable(
    registry: CapabilityRegistry,
    context: CapabilityContext,
    plan: object,
) -> bool:
    if not isinstance(plan, dict):
        return False
    steps = plan.get("steps")
    if plan.get("state") != "completed" or not isinstance(steps, list) or not steps:
        return False
    available_names = {definition.name for definition in registry.available(context)}
    for step in steps:
        if not isinstance(step, dict):
            return False
        name = step.get("capability")
        version = step.get("version")
        try:
            original = registry.resolve(name)
            compensation_name = compensation_capability_name(name)
            compensation = registry.resolve(compensation_name)
        except (CapabilityError, CapabilityCompensationError):
            return False
        if (
            original.version != version
            or original.effect is not CapabilityEffect.INTERNAL_REVERSIBLE
            or compensation_name not in available_names
            or compensation.exposure is not CapabilityExposure.HOST
            or compensation.effect is not CapabilityEffect.INTERNAL_REVERSIBLE
        ):
            return False
    return True


class CapabilityCompensationService:
    """Execute explicit host-only compensators in reverse order under the current Odoo user."""

    def __init__(
        self,
        *,
        registry: CapabilityRegistry,
        context: CapabilityContext,
        executor: CapabilityExecutor,
    ) -> None:
        self._registry = registry
        self._context = context
        self._executor = executor

    async def compensate(self, plan: object) -> CapabilityCompensationExecution:
        steps = _validated_completed_steps(plan)
        if not plan_is_compensatable(self._registry, self._context, plan):
            raise CapabilityCompensationError("capability_compensation_unavailable")
        results = []
        for step in reversed(steps):
            name = step["capability"]
            original = self._registry.resolve(name)
            if original.version != step["version"]:
                raise CapabilityCompensationError("capability_compensation_version_mismatch")
            compensation = compensation_capability_name(name)
            payload = {
                "original_capability": name,
                "original_version": step["version"],
                "arguments": dict(step["arguments"]),
                "preview": dict(step["preview"]),
                "result": dict(step["result"]),
                "verification": dict(step["verification"]),
            }
            try:
                result = await self._executor.execute(
                    compensation,
                    payload,
                    authority=ExecutionAuthority.HOST,
                    approved=True,
                )
            except CapabilityError as error:
                raise CapabilityCompensationError(error.code) from error
            if result.data.get("verified") is not True:
                raise CapabilityCompensationError("capability_compensation_verification_failed")
            results.append(result)
        return CapabilityCompensationExecution(results=tuple(results))


def _validated_completed_steps(plan: object) -> tuple[dict[str, object], ...]:
    if not isinstance(plan, dict) or plan.get("state") != "completed":
        raise CapabilityCompensationError("capability_compensation_plan_invalid")
    steps = plan.get("steps")
    if not isinstance(steps, list) or not 1 <= len(steps) <= 12:
        raise CapabilityCompensationError("capability_compensation_plan_invalid")
    normalized = []
    for position, step in enumerate(steps):
        if (
            not isinstance(step, dict)
            or step.get("position") != position
            or not isinstance(step.get("capability"), str)
            or not isinstance(step.get("version"), str)
            or not isinstance(step.get("arguments"), dict)
            or not isinstance(step.get("preview"), dict)
            or not isinstance(step.get("result"), dict)
            or not isinstance(step.get("verification"), dict)
            or step.get("state") != "completed"
        ):
            raise CapabilityCompensationError("capability_compensation_plan_invalid")
        normalized.append(dict(step))
    return tuple(normalized)
