import json
from datetime import UTC, datetime
from uuid import UUID

import pytest
from pydantic import ValidationError

from odoo_ai.contracts import (
    AnswerConfidence,
    AnswerEnvelope,
    ContextPack,
    ConversationState,
    Evidence,
    EvidenceKind,
    EvidenceSensitivity,
    EvidenceStatus,
    InstanceProfileSummary,
    ProposedAction,
    ScreenContext,
    ToolRisk,
    ToolSpec,
    TurnLimits,
    UserExecutionContext,
    UserRequest,
    Workflow,
)


def _evidence() -> Evidence:
    return Evidence(
        evidence_id=UUID("12345678-1234-5678-1234-567812345678"),
        kind=EvidenceKind.RECORD,
        status=EvidenceStatus.CHECKED,
        title="Quotation",
        summary="Quotation read under the effective user.",
        sensitivity=EvidenceSensitivity.NORMAL,
    )


def _context_pack() -> ContextPack:
    screen = ScreenContext(
        model="sale.order",
        res_id=56,
        captured_at=datetime(2026, 8, 21, 10, 30, tzinfo=UTC),
    )
    return ContextPack(
        request=UserRequest(message="Why did confirming this quotation create a task?"),
        screen=screen,
        user=UserExecutionContext(
            uid=7,
            company_id=1,
            allowed_company_ids=[1],
            lang="en_US",
        ),
        workflow_hint=Workflow.DIAGNOSE,
        instance=InstanceProfileSummary(
            instance_id="odoo-prod",
            profile_revision="rev-12",
            capabilities=["source", "logs"],
        ),
        live_evidence=[_evidence()],
        conversation_state=ConversationState(current_screen=screen),
        limits=TurnLimits(max_tool_calls=6, max_evidence_items=8),
    )


def test_context_pack_constructs_and_serializes_to_json() -> None:
    serialized = json.loads(_context_pack().model_dump_json())

    assert serialized["request"]["message"].startswith("Why")
    assert serialized["user"]["uid"] == 7
    assert serialized["workflow_hint"] == "DIAGNOSE"
    assert serialized["live_evidence"][0]["kind"] == "record"
    assert serialized["limits"] == {"max_tool_calls": 6, "max_evidence_items": 8}


def test_tool_spec_validates_risk_and_serializes() -> None:
    tool = ToolSpec(
        name="odoo.current_record",
        description="Read the current record with validated fields.",
        input_schema={
            "type": "object",
            "properties": {"fields": {"type": "array", "items": {"type": "string"}}},
        },
        risk=ToolRisk.READ,
        executor_id="odoo.current_record.v1",
    )

    assert json.loads(tool.model_dump_json())["risk"] == "read"

    with pytest.raises(ValidationError):
        ToolSpec.model_validate({**tool.model_dump(), "risk": "admin"})


def test_answer_envelope_uses_uuid_evidence_references() -> None:
    evidence_id = UUID("12345678-1234-5678-1234-567812345678")
    answer = AnswerEnvelope(
        answer_markdown="The task was created by the installed customization.",
        workflow=Workflow.EXPLAIN,
        confidence=AnswerConfidence.HIGH,
        evidence_refs=[evidence_id],
        limitations=["The write condition was not executed during this turn."],
        proposed_action=ProposedAction(
            action_type="inspect_configuration",
            summary="Review the customization setting.",
        ),
    )

    serialized = json.loads(answer.model_dump_json())

    assert serialized["evidence_refs"] == [str(evidence_id)]
    assert serialized["proposed_action"]["summary"].startswith("Review")


@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    [("workflow", "DEBUG"), ("confidence", "certain")],
)
def test_answer_envelope_rejects_invalid_enums(field_name: str, invalid_value: str) -> None:
    values = {
        "answer_markdown": "Answer",
        "workflow": "QUERY",
        "confidence": "medium",
    }
    values[field_name] = invalid_value

    with pytest.raises(ValidationError):
        AnswerEnvelope.model_validate(values)


def test_answer_envelope_rejects_non_uuid_evidence_reference() -> None:
    with pytest.raises(ValidationError):
        AnswerEnvelope(
            answer_markdown="Answer",
            workflow=Workflow.QUERY,
            confidence=AnswerConfidence.LOW,
            evidence_refs=["not-an-evidence-id"],
        )


@pytest.mark.parametrize("contract", [ContextPack, ToolSpec, AnswerEnvelope])
def test_agent_contract_json_schema_is_serializable(contract: type[object]) -> None:
    assert json.loads(json.dumps(contract.model_json_schema()))["type"] == "object"
