"""Provider-neutral bounded resource budgets for one agent turn."""

from __future__ import annotations

from dataclasses import dataclass

from .working_transcript import MAX_RESULT_BYTES, MAX_TRANSCRIPT_BYTES

_MAX_PROVIDER_DECISIONS = 32
_MAX_CAPABILITY_CALLS = 32
_MAX_CONSECUTIVE_FAILURES = 8
_MAX_EFFECT_STEPS = 5


class AgentBudgetError(RuntimeError):
    def __init__(self, code: str = "agent_policy_invalid") -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class SafetyBudget:
    max_effect_steps: int = 1
    max_consecutive_failures: int = 3


@dataclass(frozen=True, slots=True)
class ExplorationBudget:
    max_provider_decisions: int = 12
    max_capability_calls: int = 8


@dataclass(frozen=True, slots=True)
class CostBudget:
    max_provider_decisions: int = 12


@dataclass(frozen=True, slots=True)
class LatencyBudget:
    max_provider_decisions: int = 12


@dataclass(frozen=True, slots=True)
class ResponseBudget:
    max_transcript_bytes: int = MAX_TRANSCRIPT_BYTES
    max_result_bytes: int = MAX_RESULT_BYTES


@dataclass(frozen=True, slots=True)
class AgentBudgetSet:
    safety: SafetyBudget
    exploration: ExplorationBudget
    cost: CostBudget
    latency: LatencyBudget
    response: ResponseBudget

    @property
    def provider_decision_limit(self) -> int:
        return min(
            self.exploration.max_provider_decisions,
            self.cost.max_provider_decisions,
            self.latency.max_provider_decisions,
        )

    def remaining(
        self,
        *,
        provider_decisions: int,
        capability_calls: int,
        consecutive_failures: int,
        transcript_bytes: int,
    ) -> dict[str, int]:
        return {
            "provider_decisions": max(0, self.provider_decision_limit - provider_decisions),
            "capability_calls": max(
                0, self.exploration.max_capability_calls - capability_calls
            ),
            "correctable_failures": max(
                0, self.safety.max_consecutive_failures - consecutive_failures
            ),
            "effect_steps": self.safety.max_effect_steps,
            "cost_provider_decisions": max(
                0, self.cost.max_provider_decisions - provider_decisions
            ),
            "latency_provider_decisions": max(
                0, self.latency.max_provider_decisions - provider_decisions
            ),
            "transcript_bytes": max(
                0, self.response.max_transcript_bytes - transcript_bytes
            ),
            "result_bytes": self.response.max_result_bytes,
        }


def resolve_agent_budgets(context) -> AgentBudgetSet:
    """Resolve stable policy plus optional host-owned P6 budget overrides.

    Legacy/custom callers that do not receive the normalized Odoo P6 policy remain single-step.
    The product host opts into bounded multi-step through ``max_effect_steps_per_plan``. Provider
    adapters only receive remaining counters and never own these limits.
    """

    policy = context.metadata.get("capability_policy", {})
    if not isinstance(policy, dict):
        policy = {}
    overrides = context.metadata.get("agent_budgets", {})
    if not isinstance(overrides, dict):
        raise AgentBudgetError()

    exploration = _family(overrides, "exploration")
    safety = _family(overrides, "safety")
    cost = _family(overrides, "cost")
    latency = _family(overrides, "latency")
    response = _family(overrides, "response")

    provider_decisions = _bounded_int(
        exploration.get("max_provider_decisions", policy.get("max_provider_decisions", 12)),
        1,
        _MAX_PROVIDER_DECISIONS,
    )
    capability_calls = _bounded_int(
        exploration.get("max_capability_calls", policy.get("max_capability_calls", 8)),
        1,
        _MAX_CAPABILITY_CALLS,
    )
    failures = _bounded_int(
        safety.get(
            "max_consecutive_failures",
            policy.get(
                "max_consecutive_correctable_failures",
                policy.get("max_consecutive_failures", 3),
            ),
        ),
        1,
        _MAX_CONSECUTIVE_FAILURES,
    )
    policy_write_steps = policy.get("max_write_steps_per_plan", _MAX_EFFECT_STEPS)
    if type(policy_write_steps) is not int or not 0 <= policy_write_steps <= 12:
        raise AgentBudgetError()
    requested_effect_steps = _bounded_int(
        safety.get(
            "max_effect_steps",
            policy.get("max_effect_steps_per_plan", 1),
        ),
        1,
        _MAX_EFFECT_STEPS,
    )
    effect_steps = min(requested_effect_steps, policy_write_steps)

    cost_provider = _bounded_int(
        cost.get("max_provider_decisions", provider_decisions),
        1,
        _MAX_PROVIDER_DECISIONS,
    )
    latency_provider = _bounded_int(
        latency.get("max_provider_decisions", provider_decisions),
        1,
        _MAX_PROVIDER_DECISIONS,
    )
    transcript_bytes = _bounded_int(
        response.get("max_transcript_bytes", MAX_TRANSCRIPT_BYTES),
        4_096,
        MAX_TRANSCRIPT_BYTES,
    )
    result_bytes = _bounded_int(
        response.get("max_result_bytes", MAX_RESULT_BYTES),
        1_024,
        MAX_RESULT_BYTES,
    )
    if result_bytes > transcript_bytes:
        raise AgentBudgetError()

    return AgentBudgetSet(
        safety=SafetyBudget(
            max_effect_steps=effect_steps,
            max_consecutive_failures=failures,
        ),
        exploration=ExplorationBudget(
            max_provider_decisions=provider_decisions,
            max_capability_calls=capability_calls,
        ),
        cost=CostBudget(max_provider_decisions=cost_provider),
        latency=LatencyBudget(max_provider_decisions=latency_provider),
        response=ResponseBudget(
            max_transcript_bytes=transcript_bytes,
            max_result_bytes=result_bytes,
        ),
    )


def _family(overrides: dict, name: str) -> dict:
    value = overrides.get(name, {})
    if not isinstance(value, dict):
        raise AgentBudgetError()
    return value


def _bounded_int(value, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise AgentBudgetError()
    return value
