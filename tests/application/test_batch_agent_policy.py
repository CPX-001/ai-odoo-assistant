from __future__ import annotations

from odoo_ai.application.agent_policy import (
    AgentProposalBinding,
    evaluate_agent_candidate,
)
from odoo_ai.contracts import (
    AgentCandidateOutput,
    AgentCandidateStep,
    AgentPolicyLayer,
    AgentPolicyLayers,
    ConfirmationMode,
    EffectScope,
    HostToolPolicySpec,
    RiskLevel,
)

BATCH_TOOL = "odoo.preview_batch_mutation"


def _layer(
    mode: ConfirmationMode = ConfirmationMode.PROTECTED_ONLY,
    risk: RiskLevel = RiskLevel.HIGH,
) -> AgentPolicyLayer:
    return AgentPolicyLayer(
        confirmation_mode=mode,
        max_auto_risk=risk,
        allow_synthetic_data=False,
    )


def _layers(*, user_risk: RiskLevel) -> AgentPolicyLayers:
    return AgentPolicyLayers(
        system_ceiling=_layer(),
        administrator=_layer(),
        user=_layer(ConfirmationMode.RISK_BASED, user_risk),
        conversation=_layer(),
    )


def _registry() -> tuple[HostToolPolicySpec, ...]:
    return (
        HostToolPolicySpec(
            tool_name=BATCH_TOOL,
            is_write=True,
            needs_schema=True,
            effect_scope=EffectScope.INTERNAL_REVERSIBLE,
            risk_floor=RiskLevel.LOW,
            atomic=False,
            max_records=500,
            allowed_models=(),
        ),
    )


def _candidate(operation: str, *, claimed_count: int = 1) -> AgentCandidateOutput:
    return AgentCandidateOutput(
        answer_markdown="Prepararé el lote.",
        confidence="high",
        steps=(
            AgentCandidateStep(
                step_id="bulk",
                title="Aplicar lote",
                tool_name=BATCH_TOOL,
                arguments={
                    "job_id": "00000000-0000-0000-0000-000000000001",
                    "turn_id": "00000000-0000-0000-0000-000000000002",
                    "job_fingerprint": "batch-job:v1:sha256:" + "a" * 64,
                    "operation": operation,
                    "model": "res.partner",
                    "item_count": claimed_count,
                    "failure_mode": "continue_on_error",
                    "source_provider": "agent.turn",
                    "source_display_name": "Agent turn batch",
                },
            ),
        ),
    )


def test_host_observed_count_drives_blast_radius_and_large_batch_risk() -> None:
    evaluated = evaluate_agent_candidate(
        _candidate("create", claimed_count=1),
        registry=_registry(),
        layers=_layers(user_risk=RiskLevel.MODERATE),
        proposal_bindings={"bulk": AgentProposalBinding(estimated_records=200)},
    )

    assert evaluated.steps[0].estimated_records == 200
    assert evaluated.metadata.estimated_blast_radius == 200
    assert evaluated.risk is RiskLevel.HIGH
    assert evaluated.requires_confirmation is True


def test_batch_delete_is_protected_and_irreversible() -> None:
    evaluated = evaluate_agent_candidate(
        _candidate("delete", claimed_count=3),
        registry=_registry(),
        layers=_layers(user_risk=RiskLevel.HIGH),
        proposal_bindings={"bulk": AgentProposalBinding(estimated_records=3)},
    )

    assert evaluated.steps[0].effect_scope is EffectScope.INTERNAL_IRREVERSIBLE
    assert evaluated.risk is RiskLevel.PROTECTED
    assert evaluated.metadata.has_irreversible_effect is True
    assert evaluated.requires_confirmation is True


def test_batch_create_remains_reversible_and_small_count_does_not_inflate() -> None:
    evaluated = evaluate_agent_candidate(
        _candidate("create", claimed_count=500),
        registry=_registry(),
        layers=_layers(user_risk=RiskLevel.MODERATE),
        proposal_bindings={"bulk": AgentProposalBinding(estimated_records=2)},
    )

    assert evaluated.steps[0].estimated_records == 2
    assert evaluated.steps[0].effect_scope is EffectScope.INTERNAL_REVERSIBLE
    assert evaluated.risk is RiskLevel.LOW
    assert evaluated.requires_confirmation is False
