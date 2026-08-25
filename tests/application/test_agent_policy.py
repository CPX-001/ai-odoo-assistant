import pytest
from odoo_ai.application.agent_policy import (
    evaluate_agent_candidate,
    intersect_agent_policy,
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


def _layer(
    mode: ConfirmationMode = ConfirmationMode.PROTECTED_ONLY,
    risk: RiskLevel = RiskLevel.HIGH,
    *,
    synthetic: bool = True,
) -> AgentPolicyLayer:
    return AgentPolicyLayer(
        confirmation_mode=mode,
        max_auto_risk=risk,
        allow_synthetic_data=synthetic,
    )


def _layers(*, user_risk: RiskLevel = RiskLevel.LOW) -> AgentPolicyLayers:
    return AgentPolicyLayers(
        system_ceiling=_layer(),
        administrator=_layer(),
        user=_layer(ConfirmationMode.RISK_BASED, user_risk),
        conversation=_layer(),
    )


def _tool(
    name: str,
    risk: RiskLevel,
    *,
    scope: EffectScope = EffectScope.INTERNAL_REVERSIBLE,
    atomic: bool = True,
    business: bool = False,
    records: int = 1,
) -> HostToolPolicySpec:
    return HostToolPolicySpec(
        tool_name=name,
        is_write=True,
        effect_scope=scope,
        risk_floor=risk,
        atomic=atomic,
        is_business_action=business,
        max_records=records,
    )


def test_user_autonomy_controls_confirmation_even_if_hidden_layers_are_stricter() -> None:
    layers = AgentPolicyLayers(
        system_ceiling=_layer(ConfirmationMode.ALWAYS_CONFIRM, RiskLevel.LOW),
        administrator=_layer(ConfirmationMode.RISK_BASED, RiskLevel.MODERATE),
        user=_layer(ConfirmationMode.PROTECTED_ONLY, RiskLevel.PROTECTED),
        conversation=_layer(ConfirmationMode.ALWAYS_CONFIRM, RiskLevel.LOW),
    )

    effective = intersect_agent_policy(layers)

    assert effective.confirmation_mode is ConfirmationMode.PROTECTED_ONLY
    assert effective.max_auto_risk is RiskLevel.PROTECTED
    assert effective.fingerprint.startswith("agent-policy:v1:sha256:")
    assert "user" in effective.constrained_by


def test_hidden_layers_can_still_reduce_technical_budgets_and_synthetic_data() -> None:
    system = AgentPolicyLayer(
        confirmation_mode=ConfirmationMode.ALWAYS_CONFIRM,
        max_auto_risk=RiskLevel.LOW,
        allow_synthetic_data=False,
        max_tool_calls_per_turn=8,
        max_write_steps_per_plan=4,
        max_replans=1,
        max_consecutive_failures=2,
    )
    user = AgentPolicyLayer(
        confirmation_mode=ConfirmationMode.PROTECTED_ONLY,
        max_auto_risk=RiskLevel.PROTECTED,
        allow_synthetic_data=True,
    )
    layers = AgentPolicyLayers(
        system_ceiling=system,
        administrator=_layer(),
        user=user,
        conversation=_layer(),
    )

    effective = intersect_agent_policy(layers)

    assert effective.confirmation_mode is ConfirmationMode.PROTECTED_ONLY
    assert effective.max_auto_risk is RiskLevel.PROTECTED
    assert effective.allow_synthetic_data is False
    assert effective.max_tool_calls_per_turn == 8
    assert effective.max_write_steps_per_plan == 4
    assert effective.max_replans == 1
    assert effective.max_consecutive_failures == 2
    assert "system_ceiling" in effective.constrained_by


def test_low_single_write_executes_without_confirmation() -> None:
    candidate = AgentCandidateOutput(
        answer_markdown="Crearé el contacto.",
        confidence="high",
        steps=(
            AgentCandidateStep(
                step_id="create_contact",
                title="Crear contacto",
                tool_name="odoo.preview_record_create",
                arguments={"model": "res.partner"},
            ),
        ),
    )

    evaluated = evaluate_agent_candidate(
        candidate,
        registry=(_tool("odoo.preview_record_create", RiskLevel.LOW),),
        layers=_layers(),
    )

    assert evaluated.risk is RiskLevel.LOW
    assert evaluated.requires_confirmation is False
    assert evaluated.metadata.needs_write is True


def test_non_atomic_dependent_writes_raise_risk_without_summing() -> None:
    candidate = AgentCandidateOutput(
        answer_markdown="Crearé el contacto y el presupuesto.",
        confidence="high",
        steps=(
            AgentCandidateStep(
                step_id="contact",
                title="Crear contacto",
                tool_name="contact.create",
                arguments={"model": "res.partner"},
            ),
            AgentCandidateStep(
                step_id="quotation",
                title="Crear presupuesto",
                tool_name="quotation.create",
                arguments={"model": "sale.order"},
                depends_on=("contact",),
            ),
        ),
    )

    evaluated = evaluate_agent_candidate(
        candidate,
        registry=(
            _tool("contact.create", RiskLevel.LOW, atomic=False),
            _tool("quotation.create", RiskLevel.LOW, atomic=False),
        ),
        layers=_layers(),
    )

    assert evaluated.risk is RiskLevel.HIGH
    assert evaluated.requires_confirmation is True
    assert evaluated.metadata.estimated_blast_radius == 2


def test_splitting_one_model_write_does_not_preserve_low_risk() -> None:
    candidate = AgentCandidateOutput(
        answer_markdown="Actualizaré ambos campos.",
        confidence="high",
        steps=(
            AgentCandidateStep(
                step_id="first_patch",
                title="Actualizar teléfono",
                tool_name="record.patch",
                arguments={"model": "res.partner", "record_id": 7},
            ),
            AgentCandidateStep(
                step_id="second_patch",
                title="Actualizar ciudad",
                tool_name="record.patch",
                arguments={"model": "res.partner", "record_id": 7},
                depends_on=("first_patch",),
            ),
        ),
    )

    evaluated = evaluate_agent_candidate(
        candidate,
        registry=(_tool("record.patch", RiskLevel.LOW, atomic=False),),
        layers=_layers(user_risk=RiskLevel.MODERATE),
    )

    assert evaluated.metadata.is_atomic is False
    assert evaluated.risk is RiskLevel.MODERATE


def test_atomic_business_action_uses_flow_risk_instead_of_substep_count() -> None:
    candidate = AgentCandidateOutput(
        answer_markdown="Crearé y confirmaré el presupuesto.",
        confidence="high",
        steps=(
            AgentCandidateStep(
                step_id="sale_flow",
                title="Crear y confirmar presupuesto",
                tool_name="sale.order.build_flow.v1",
                arguments={"model": "sale.order", "end_state": "sale_order"},
            ),
        ),
    )

    evaluated = evaluate_agent_candidate(
        candidate,
        registry=(
            _tool(
                "sale.order.build_flow.v1",
                RiskLevel.MODERATE,
                atomic=True,
                business=True,
                records=3,
            ),
        ),
        layers=_layers(user_risk=RiskLevel.MODERATE),
    )

    assert evaluated.risk is RiskLevel.MODERATE
    assert evaluated.requires_confirmation is False
    assert evaluated.metadata.is_atomic is True


@pytest.mark.parametrize(
    ("end_state", "expected"),
    [
        ("quotation", RiskLevel.LOW),
        ("sale_order", RiskLevel.MODERATE),
        ("invoice_draft", RiskLevel.HIGH),
    ],
)
def test_sale_flow_uses_the_registered_whole_flow_risk(
    end_state: str, expected: RiskLevel
) -> None:
    candidate = AgentCandidateOutput(
        answer_markdown="Prepararé el flujo solicitado.",
        confidence="high",
        steps=(
            AgentCandidateStep(
                step_id="sale_flow",
                title="Preparar venta",
                tool_name="odoo.preview_sale_order_build_flow",
                arguments={"end_state": end_state},
            ),
        ),
    )

    evaluated = evaluate_agent_candidate(
        candidate,
        registry=(
            _tool(
                "odoo.preview_sale_order_build_flow",
                RiskLevel.LOW,
                atomic=True,
                business=True,
                records=3,
            ),
        ),
        layers=_layers(user_risk=RiskLevel.HIGH),
    )

    assert evaluated.risk is expected


def test_external_or_irreversible_effect_is_protected_but_full_access_can_run_it() -> None:
    candidate = AgentCandidateOutput(
        answer_markdown="Eliminaré el registro.",
        confidence="high",
        steps=(
            AgentCandidateStep(
                step_id="delete",
                title="Eliminar registro",
                tool_name="record.delete",
                arguments={"model": "res.partner"},
            ),
        ),
    )

    autonomous = evaluate_agent_candidate(
        candidate,
        registry=(
            _tool(
                "record.delete",
                RiskLevel.PROTECTED,
                scope=EffectScope.INTERNAL_IRREVERSIBLE,
            ),
        ),
        layers=AgentPolicyLayers(
            system_ceiling=_layer(),
            administrator=_layer(),
            user=_layer(ConfirmationMode.PROTECTED_ONLY, RiskLevel.HIGH),
            conversation=_layer(),
        ),
    )
    full_access = evaluate_agent_candidate(
        candidate,
        registry=(
            _tool(
                "record.delete",
                RiskLevel.PROTECTED,
                scope=EffectScope.INTERNAL_IRREVERSIBLE,
            ),
        ),
        layers=AgentPolicyLayers(
            system_ceiling=_layer(ConfirmationMode.ALWAYS_CONFIRM, RiskLevel.LOW),
            administrator=_layer(),
            user=_layer(ConfirmationMode.PROTECTED_ONLY, RiskLevel.PROTECTED),
            conversation=_layer(ConfirmationMode.ALWAYS_CONFIRM, RiskLevel.LOW),
        ),
    )

    assert autonomous.risk is RiskLevel.PROTECTED
    assert autonomous.requires_confirmation is True
    assert full_access.risk is RiskLevel.PROTECTED
    assert full_access.requires_confirmation is False
