"""Deterministic host-side policy intersection and aggregate plan risk."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from uuid import UUID

from odoo_ai.contracts.agent_turn import (
    AgentCandidateOutput,
    AgentPlanMetadata,
    AgentPlanStep,
    AgentPolicyLayer,
    AgentPolicyLayers,
    ConfirmationMode,
    EffectiveAgentPolicy,
    EffectScope,
    HostToolPolicySpec,
    PolicyLayerName,
    RiskLevel,
)

POLICY_REVISION = "agent-policy-v2"
_MODE_ORDER = {
    ConfirmationMode.ALWAYS_CONFIRM: 0,
    ConfirmationMode.RISK_BASED: 1,
    ConfirmationMode.PROTECTED_ONLY: 2,
}
_RISK_ORDER = {
    RiskLevel.LOW: 0,
    RiskLevel.MODERATE: 1,
    RiskLevel.HIGH: 2,
    RiskLevel.PROTECTED: 3,
}


class AgentPolicyError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class EvaluatedAgentPlan:
    policy: EffectiveAgentPolicy
    steps: tuple[AgentPlanStep, ...]
    metadata: AgentPlanMetadata
    risk: RiskLevel
    requires_confirmation: bool


@dataclass(frozen=True, slots=True)
class AgentProposalBinding:
    proposal_id: UUID
    payload_fingerprint: str


def intersect_agent_policy(layers: AgentPolicyLayers) -> EffectiveAgentPolicy:
    named_values: tuple[tuple[PolicyLayerName, AgentPolicyLayer], ...] = (
        ("system_ceiling", layers.system_ceiling),
        ("administrator", layers.administrator),
        ("user", layers.user),
        ("conversation", layers.conversation),
    )
    values = tuple(value for _, value in named_values)
    mode = min(values, key=lambda value: _MODE_ORDER[value.confirmation_mode]).confirmation_mode
    max_risk = min(values, key=lambda value: _RISK_ORDER[value.max_auto_risk]).max_auto_risk
    payload = AgentPolicyLayer(
        confirmation_mode=mode,
        max_auto_risk=max_risk,
        allow_synthetic_data=all(value.allow_synthetic_data for value in values),
        max_tool_calls_per_turn=min(value.max_tool_calls_per_turn for value in values),
        max_write_steps_per_plan=min(value.max_write_steps_per_plan for value in values),
        max_replans=min(value.max_replans for value in values),
        max_consecutive_failures=min(value.max_consecutive_failures for value in values),
    )
    fingerprint = agent_policy_fingerprint(payload)
    autonomy_varies = (
        len({value.confirmation_mode for value in values}) > 1
        or len({value.max_auto_risk for value in values}) > 1
        or len({value.allow_synthetic_data for value in values}) > 1
    )
    constrained_by: tuple[PolicyLayerName, ...] = tuple(
        name
        for name, value in named_values
        if (value.confirmation_mode == mode and len({item.confirmation_mode for item in values}) > 1)
        or (value.max_auto_risk == max_risk and len({item.max_auto_risk for item in values}) > 1)
        or (
            not payload.allow_synthetic_data
            and not value.allow_synthetic_data
            and len({item.allow_synthetic_data for item in values}) > 1
        )
    )
    if not autonomy_varies:
        constrained_by = ("system_ceiling",)
    return EffectiveAgentPolicy(
        **payload.model_dump(),
        revision=POLICY_REVISION,
        fingerprint=fingerprint,
        constrained_by=constrained_by,
    )


def evaluate_agent_candidate(
    candidate: AgentCandidateOutput,
    *,
    registry: Sequence[HostToolPolicySpec],
    layers: AgentPolicyLayers,
    proposal_bindings: Mapping[str, AgentProposalBinding] | None = None,
) -> EvaluatedAgentPlan:
    policy = intersect_agent_policy(layers)
    specs = {spec.tool_name: spec for spec in registry}
    if len(specs) != len(registry):
        raise AgentPolicyError("agent_tool_registry_invalid")
    normalized: list[AgentPlanStep] = []
    bindings = {} if proposal_bindings is None else dict(proposal_bindings)
    for proposed in candidate.steps:
        spec = specs.get(proposed.tool_name)
        if spec is None:
            raise AgentPolicyError("agent_tool_not_registered")
        model = proposed.arguments.get("model")
        if spec.allowed_models and model is not None and (
            not isinstance(model, str) or model not in spec.allowed_models
        ):
            raise AgentPolicyError("agent_model_not_allowed")
        step_payload = {
            "arguments": proposed.arguments,
            "depends_on": proposed.depends_on,
            "step_id": proposed.step_id,
            "tool_name": proposed.tool_name,
        }
        binding = bindings.get(proposed.step_id)
        normalized.append(
            AgentPlanStep(
                step_id=proposed.step_id,
                title=proposed.title,
                tool_name=proposed.tool_name,
                arguments=proposed.arguments,
                depends_on=proposed.depends_on,
                risk=_typed_action_risk(spec, proposed.arguments),
                effect_scope=spec.effect_scope,
                is_write=spec.is_write,
                is_business_action=spec.is_business_action,
                atomic=spec.atomic,
                estimated_records=spec.max_records,
                payload_fingerprint=_fingerprint("agent-step", step_payload),
                proposal_id=(binding.proposal_id if binding is not None else None),
                proposal_fingerprint=(
                    binding.payload_fingerprint if binding is not None else None
                ),
            )
        )
    write_steps = tuple(step for step in normalized if step.is_write)
    if len(write_steps) > policy.max_write_steps_per_plan:
        raise AgentPolicyError("agent_plan_write_limit_exceeded")
    metadata = _derive_metadata(tuple(normalized), write_steps)
    risk = _aggregate_risk(write_steps, metadata)
    return EvaluatedAgentPlan(
        policy=policy,
        steps=tuple(normalized),
        metadata=metadata,
        risk=risk,
        requires_confirmation=_requires_confirmation(policy, risk, bool(write_steps)),
    )


def agent_policy_fingerprint(policy: AgentPolicyLayer) -> str:
    """Bind every autonomy and anti-loop field, excluding display-only provenance."""

    payload = {
        "allow_synthetic_data": policy.allow_synthetic_data,
        "confirmation_mode": policy.confirmation_mode.value,
        "max_auto_risk": policy.max_auto_risk.value,
        "max_consecutive_failures": policy.max_consecutive_failures,
        "max_replans": policy.max_replans,
        "max_tool_calls_per_turn": policy.max_tool_calls_per_turn,
        "max_write_steps_per_plan": policy.max_write_steps_per_plan,
    }
    return _fingerprint("agent-policy", payload)


def _derive_metadata(
    steps: tuple[AgentPlanStep, ...], write_steps: tuple[AgentPlanStep, ...]
) -> AgentPlanMetadata:
    return AgentPlanMetadata(
        needs_read=any(not step.is_write for step in steps),
        needs_schema=any(step.is_write and "schema_id" in step.arguments for step in steps),
        needs_write=bool(write_steps),
        needs_business_action=any(step.is_business_action for step in steps),
        has_external_effect=any(step.effect_scope is EffectScope.EXTERNAL for step in steps),
        has_irreversible_effect=any(
            step.effect_scope is EffectScope.INTERNAL_IRREVERSIBLE for step in steps
        ),
        is_atomic=not write_steps or len(write_steps) == 1 and write_steps[0].atomic,
        estimated_blast_radius=sum(step.estimated_records for step in write_steps),
    )


def _typed_action_risk(
    spec: HostToolPolicySpec, arguments: Mapping[str, object]
) -> RiskLevel:
    """Apply the registered whole-flow risk for versioned typed business actions."""

    if spec.tool_name == "odoo.preview_sale_order_build_flow":
        end_state = arguments.get("end_state")
        if not isinstance(end_state, str):
            return RiskLevel.HIGH
        return {
            "quotation": RiskLevel.LOW,
            "sale_order": RiskLevel.MODERATE,
            "invoice_draft": RiskLevel.HIGH,
        }.get(end_state, RiskLevel.HIGH)
    return spec.risk_floor


def _aggregate_risk(
    write_steps: tuple[AgentPlanStep, ...], metadata: AgentPlanMetadata
) -> RiskLevel:
    if not write_steps:
        return RiskLevel.LOW
    if metadata.has_external_effect or metadata.has_irreversible_effect:
        return RiskLevel.PROTECTED
    risk = max((step.risk for step in write_steps), key=_RISK_ORDER.__getitem__)
    model_names = {
        model
        for step in write_steps
        if isinstance((model := step.arguments.get("model")), str)
    }
    if metadata.estimated_blast_radius > 3 or len(model_names) > 1:
        risk = _at_least(risk, RiskLevel.MODERATE)
    if metadata.estimated_blast_radius > 12:
        raise AgentPolicyError("agent_plan_blast_radius_exceeded")
    one_atomic_business_action = (
        len(write_steps) == 1 and write_steps[0].is_business_action and write_steps[0].atomic
    )
    if len(write_steps) > 1 and not metadata.is_atomic and not one_atomic_business_action:
        risk = _raise_one(risk)
    return risk


def _requires_confirmation(
    policy: EffectiveAgentPolicy, risk: RiskLevel, has_writes: bool
) -> bool:
    if not has_writes:
        return False
    if policy.confirmation_mode is ConfirmationMode.ALWAYS_CONFIRM:
        return True
    return _RISK_ORDER[risk] > _RISK_ORDER[policy.max_auto_risk]


def _at_least(value: RiskLevel, floor: RiskLevel) -> RiskLevel:
    return value if _RISK_ORDER[value] >= _RISK_ORDER[floor] else floor


def _raise_one(value: RiskLevel) -> RiskLevel:
    if value is RiskLevel.LOW:
        return RiskLevel.MODERATE
    if value is RiskLevel.MODERATE:
        return RiskLevel.HIGH
    return value


def _fingerprint(domain: str, value: Mapping[str, object]) -> str:
    body = json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return f"{domain}:v1:sha256:{hashlib.sha256(body).hexdigest()}"
