from datetime import UTC, datetime, timedelta
from uuid import uuid4

from odoo_ai.application.agent_turn import _execution_answer
from odoo_ai.contracts import (
    AgentPlanMetadata,
    AgentPlanReceiptView,
    AgentPlanStatusResponse,
    AgentPlanStepView,
    AgentPlanView,
    AgentPolicyView,
    ConfirmationMode,
    EffectScope,
    PlanState,
    RiskLevel,
)

NOW = datetime(2026, 8, 24, 21, 30, tzinfo=UTC)


def _status(
    state: PlanState,
    *,
    step_states=("completed",),
    error_code: str | None = None,
) -> AgentPlanStatusResponse:
    steps = tuple(
        AgentPlanStepView(
            step_id=f"step_{index}",
            title=f"Operación {index}",
            state=step_state,
            risk=RiskLevel.PROTECTED,
            effect_scope=EffectScope.INTERNAL_IRREVERSIBLE,
            receipt=(
                AgentPlanReceiptView(
                    outcome="failed" if step_state == "failed" else "verified",
                    error_code=error_code if step_state == "failed" else None,
                )
                if step_state in {"completed", "failed"}
                else None
            ),
        )
        for index, step_state in enumerate(step_states, start=1)
    )
    completed_at = (
        NOW + timedelta(seconds=1)
        if state in {PlanState.COMPLETED, PlanState.PARTIAL, PlanState.FAILED}
        else None
    )
    return AgentPlanStatusResponse(
        plan=AgentPlanView(
            plan_id=uuid4(),
            state=state,
            risk=RiskLevel.PROTECTED,
            metadata=AgentPlanMetadata(
                needs_read=False,
                needs_schema=False,
                needs_write=True,
                needs_business_action=True,
                has_external_effect=False,
                has_irreversible_effect=True,
                is_atomic=len(steps) == 1,
                estimated_blast_radius=len(steps),
            ),
            policy=AgentPolicyView(
                confirmation_mode=ConfirmationMode.PROTECTED_ONLY,
                max_auto_risk=RiskLevel.PROTECTED,
                allow_synthetic_data=True,
                constrained_by=("user",),
            ),
            goal="Ejecutar operación solicitada",
            steps=steps,
            requires_confirmation=False,
            expires_at=None,
        ),
        answer_markdown="He preparado una previsualización; todavía no se ha ejecutado.",
        error_code=error_code,
        completed_at=completed_at,
    )


def test_completed_auto_execution_does_not_repeat_preview_text() -> None:
    answer = _execution_answer(_status(PlanState.COMPLETED))

    assert "Hecho" in answer
    assert "verificó" in answer
    assert "previsualización" not in answer


def test_failed_business_rule_is_reported_as_odoo_rejection() -> None:
    answer = _execution_answer(
        _status(
            PlanState.FAILED,
            step_states=("failed",),
            error_code="business_rule_rejected",
        )
    )

    assert "No se pudo completar" in answer
    assert "regla de negocio" in answer


def test_failed_access_is_not_presented_as_an_approval_problem() -> None:
    answer = _execution_answer(
        _status(
            PlanState.FAILED,
            step_states=("failed",),
            error_code="access_denied",
        )
    )

    assert "permisos actuales" in answer
    assert "confirm" not in answer.casefold()


def test_partial_execution_reports_applied_and_failed_counts() -> None:
    answer = _execution_answer(
        _status(
            PlanState.PARTIAL,
            step_states=("completed", "failed", "skipped"),
            error_code="business_rule_rejected",
        )
    )

    assert "1 completadas" in answer
    assert "1 fallidas" in answer
    assert "1 omitidas" in answer


def test_ambiguous_batch_is_presented_as_recovery_not_failure() -> None:
    answer = _execution_answer(
        _status(
            PlanState.AUTHORIZED,
            step_states=("completed", "planned"),
            error_code="batch_execution_outcome_unknown",
        )
    )

    assert "Recuperación pendiente" in answer
    assert "misma autorización" in answer
    assert "mismo intento idempotente" in answer
    assert "No se pudo completar" not in answer
