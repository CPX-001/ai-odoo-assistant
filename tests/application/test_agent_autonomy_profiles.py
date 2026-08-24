import re

import pytest
from odoo_ai.application.agent_policy import evaluate_agent_candidate
from odoo_ai.application.agent_turn import _autonomy_capability
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


@pytest.mark.parametrize(
    ("mode", "risk"),
    [
        (ConfirmationMode.ALWAYS_CONFIRM, RiskLevel.LOW),
        (ConfirmationMode.RISK_BASED, RiskLevel.MODERATE),
        (ConfirmationMode.PROTECTED_ONLY, RiskLevel.HIGH),
        (ConfirmationMode.PROTECTED_ONLY, RiskLevel.PROTECTED),
    ],
)
def test_autonomy_profile_is_a_valid_context_capability(
    mode: ConfirmationMode,
    risk: RiskLevel,
) -> None:
    capability = _autonomy_capability(mode, risk)

    assert len(capability) <= 128
    assert re.fullmatch(r"[A-Za-z0-9_.:-]+", capability)


def _layer(mode=ConfirmationMode.PROTECTED_ONLY, risk=RiskLevel.PROTECTED):
    return AgentPolicyLayer(
        confirmation_mode=mode,
        max_auto_risk=risk,
        allow_synthetic_data=True,
    )


def _layers(user):
    permissive = _layer()
    return AgentPolicyLayers(
        system_ceiling=permissive,
        administrator=permissive,
        user=user,
        conversation=permissive,
    )


def _candidate():
    return AgentCandidateOutput(
        answer_markdown="Ejecutaré la operación solicitada.",
        confidence="high",
        steps=(
            AgentCandidateStep(
                step_id="write",
                title="Aplicar cambio",
                tool_name="test.write",
                arguments={"model": "sale.order"},
            ),
        ),
    )


def _evaluate(user, risk, scope=EffectScope.INTERNAL_REVERSIBLE):
    return evaluate_agent_candidate(
        _candidate(),
        registry=(
            HostToolPolicySpec(
                tool_name="test.write",
                is_write=True,
                effect_scope=scope,
                risk_floor=risk,
                atomic=True,
                max_records=1,
            ),
        ),
        layers=_layers(user),
    )


def test_strict_confirms_even_low_risk_writes():
    result = _evaluate(_layer(ConfirmationMode.ALWAYS_CONFIRM, RiskLevel.LOW), RiskLevel.LOW)
    assert result.requires_confirmation is True


def test_balanced_runs_moderate_but_confirms_high_risk():
    policy = _layer(ConfirmationMode.RISK_BASED, RiskLevel.MODERATE)
    assert _evaluate(policy, RiskLevel.MODERATE).requires_confirmation is False
    assert _evaluate(policy, RiskLevel.HIGH).requires_confirmation is True


def test_autonomous_only_stops_protected_operations():
    policy = _layer(ConfirmationMode.PROTECTED_ONLY, RiskLevel.HIGH)
    assert _evaluate(policy, RiskLevel.HIGH).requires_confirmation is False
    protected = _evaluate(
        policy,
        RiskLevel.PROTECTED,
        scope=EffectScope.INTERNAL_IRREVERSIBLE,
    )
    assert protected.risk is RiskLevel.PROTECTED
    assert protected.requires_confirmation is True


def test_full_access_does_not_add_confirmation_for_protected_delete():
    policy = _layer(ConfirmationMode.PROTECTED_ONLY, RiskLevel.PROTECTED)
    result = _evaluate(
        policy,
        RiskLevel.PROTECTED,
        scope=EffectScope.INTERNAL_IRREVERSIBLE,
    )
    assert result.risk is RiskLevel.PROTECTED
    assert result.requires_confirmation is False
