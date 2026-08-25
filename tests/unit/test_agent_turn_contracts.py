from datetime import UTC, datetime
from uuid import uuid4

import pytest
from odoo_ai.contracts import (
    AgentCandidateOutput,
    AgentCandidateStep,
    AgentModelCandidate,
    AgentPolicyLayer,
    AgentPolicyLayers,
    AgentTurnRequest,
    ConfirmationMode,
    OdooGatewayReference,
    RiskLevel,
    ScreenContext,
    UserExecutionContext,
)
from odoo_ai.contracts.chat import ChatActor
from pydantic import ValidationError


def test_candidate_steps_cannot_reference_future_steps() -> None:
    with pytest.raises(ValidationError):
        AgentCandidateOutput(
            answer_markdown="Plan",
            confidence="low",
            steps=(
                AgentCandidateStep(
                    step_id="first",
                    title="Primero",
                    tool_name="odoo.read",
                    arguments={},
                    depends_on=("second",),
                ),
                AgentCandidateStep(
                    step_id="second",
                    title="Segundo",
                    tool_name="odoo.read",
                    arguments={},
                ),
            ),
        )


def test_candidate_output_has_no_authorization_or_commit_fields() -> None:
    schema = AgentCandidateOutput.model_json_schema()

    assert set(schema["properties"]) == {
        "answer_markdown",
        "assumptions",
        "clarification_question",
        "confidence",
        "steps",
    }


def test_agent_request_binds_actor_to_odoo_context() -> None:
    layer = AgentPolicyLayer(
        confirmation_mode=ConfirmationMode.RISK_BASED,
        max_auto_risk=RiskLevel.LOW,
    )
    payload = {
        "turn_id": uuid4(),
        "actor": ChatActor(database="odoo", uid=7),
        "message": "Crea un contacto de prueba",
        "screen": ScreenContext(captured_at=datetime.now(UTC)),
        "user": UserExecutionContext(uid=8, company_id=1, allowed_company_ids=[1]),
        "gateway": OdooGatewayReference(database="odoo"),
        "capability_token": "opaque",
        "candidates": (AgentModelCandidate(model="res.partner"),),
        "policy_layers": AgentPolicyLayers(
            system_ceiling=layer,
            administrator=layer,
            user=layer,
            conversation=layer,
        ),
    }

    with pytest.raises(ValidationError):
        AgentTurnRequest(**payload)
