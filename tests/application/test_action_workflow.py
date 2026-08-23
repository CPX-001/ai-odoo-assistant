import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from odoo_ai.adapters import action_tool_specs
from odoo_ai.application import ActionService, ActionTurnError
from odoo_ai.contracts import (
    ActionPreviewChange,
    ActionProposalHandle,
    ActionTarget,
    ActionToolReport,
    ActionTurnRequest,
    ActionValue,
    ActionValueKind,
    AnswerConfidence,
    AnswerEnvelope,
    Evidence,
    EvidenceKind,
    EvidenceSensitivity,
    EvidenceStatus,
    ProposedAction,
    ToolExecutionReport,
    Workflow,
)

NOW = datetime(2026, 8, 23, 12, 0, tzinfo=UTC)
TURN_ID = UUID("50000000-0000-4000-8000-000000000005")
PROPOSAL_ID = UUID("60000000-0000-4000-8000-000000000006")
EVIDENCE_ID = UUID("70000000-0000-4000-8000-000000000007")
FINGERPRINT = "action-payload:v1:sha256:" + "a" * 64
PRECONDITION = "action-precondition:v1:sha256:" + "b" * 64
TOKEN = "p1." + "x" * 256


class FakeEngine:
    def __init__(self, answer: AnswerEnvelope) -> None:
        self.answer = answer
        self.context = None

    async def run_turn(self, context, tools, output_schema):
        self.context = context
        assert [tool.name for tool in tools] == [
            "odoo.get_effective_write_schema",
            "odoo.preview_record_patch",
        ]
        assert output_schema == AnswerEnvelope.model_json_schema()
        return self.answer


class ReportHolder:
    def __init__(self, report: ActionToolReport) -> None:
        self.report = report

    def take(self) -> ActionToolReport:
        result = self.report
        self.report = ActionToolReport()
        return result


def _request() -> ActionTurnRequest:
    return ActionTurnRequest.model_validate(
        {
            "turn_id": str(TURN_ID),
            "message": "Cambia el nombre",
            "screen": {
                "view_type": "form",
                "model": "res.partner",
                "res_id": 42,
                "selected_ids": [],
                "captured_at": NOW.isoformat(),
            },
            "user": {
                "uid": 17,
                "company_id": 3,
                "allowed_company_ids": [3],
                "lang": "es_ES",
            },
            "delegation_token": TOKEN,
            "gateway": {"database": "fixture-db"},
        }
    )


def _handle(*, turn_id: UUID = TURN_ID) -> ActionProposalHandle:
    return ActionProposalHandle(
        proposal_id=PROPOSAL_ID,
        turn_id=turn_id,
        payload_fingerprint=FINGERPRINT,
        precondition_fingerprint=PRECONDITION,
        target=ActionTarget(model="res.partner", record_id=42),
        changes=(
            ActionPreviewChange(
                field="name",
                label="Name",
                before=ActionValue(kind=ActionValueKind.TEXT, value="Before"),
                after=ActionValue(kind=ActionValueKind.TEXT, value="After"),
            ),
        ),
        warnings=("Approval required.",),
        expires_at=NOW + timedelta(minutes=2),
        evidence_id=EVIDENCE_ID,
    )


def _evidence() -> Evidence:
    return Evidence(
        evidence_id=EVIDENCE_ID,
        kind=EvidenceKind.RECORD,
        status=EvidenceStatus.CHECKED,
        title="preview",
        summary="checked",
        payload={"proposal_id": str(PROPOSAL_ID)},
        pointer={
            "provider": "odoo_action_preview",
            "model": "res.partner",
            "record_id": 42,
            "proposal_id": str(PROPOSAL_ID),
        },
        observed_at=NOW,
        sensitivity=EvidenceSensitivity.NORMAL,
        fingerprint=PRECONDITION,
    )


def _answer(**updates) -> AnswerEnvelope:
    values = {
        "answer_markdown": "La preview está lista para aprobación explícita.",
        "workflow": Workflow.ACTION,
        "confidence": AnswerConfidence.HIGH,
        "evidence_refs": [EVIDENCE_ID],
        "limitations": [],
        "proposed_action": ProposedAction(
            action_type="record_patch",
            summary="Cambiar Name",
            details={
                "proposal_id": str(PROPOSAL_ID),
                "payload_fingerprint": FINGERPRINT,
            },
        ),
    }
    values.update(updates)
    return AnswerEnvelope(**values)


def _service(answer: AnswerEnvelope, handle: ActionProposalHandle | None = None):
    report = ActionToolReport(
        tool_report=ToolExecutionReport(retrieved_evidence=(_evidence(),)),
        proposals=(() if handle is None else (handle,)),
    )
    engine = FakeEngine(answer)
    service = ActionService(
        reasoning_engine=engine,
        action_tools=action_tool_specs(),
        report_loader=ReportHolder(report).take,
        clock=lambda: NOW,
    )
    return service, engine


def test_action_response_uses_only_real_same_turn_proposal_and_checked_evidence() -> None:
    service, engine = _service(_answer(), _handle())

    response = asyncio.run(service.run(_request()))

    assert response.workflow is Workflow.ACTION
    assert response.proposal == _handle()
    assert response.evidence_refs == (EVIDENCE_ID,)
    assert engine.context.workflow_hint is Workflow.ACTION
    assert TOKEN not in response.model_dump_json()


@pytest.mark.parametrize(
    "answer,handle,error",
    [
        (_answer(), None, "action_proposal_not_produced"),
        (
            _answer(
                proposed_action=ProposedAction(
                    action_type="record_patch",
                    summary="invented",
                    details={
                        "proposal_id": str(UUID(int=99)),
                        "payload_fingerprint": FINGERPRINT,
                    },
                )
            ),
            _handle(),
            "action_proposal_mismatch",
        ),
        (_answer(), _handle(turn_id=UUID(int=88)), "action_proposal_mismatch"),
    ],
)
def test_invented_missing_or_cross_turn_proposal_is_rejected(answer, handle, error) -> None:
    service, _ = _service(answer, handle)

    with pytest.raises(ActionTurnError, match=error):
        asyncio.run(service.run(_request()))


def test_no_preview_requires_low_confidence_and_explicit_limitation() -> None:
    no_preview = _answer(
        confidence=AnswerConfidence.LOW,
        evidence_refs=[],
        limitations=["No se pudo producir una preview segura."],
        proposed_action=None,
    )
    report = ActionToolReport()
    engine = FakeEngine(no_preview)
    service = ActionService(
        reasoning_engine=engine,
        action_tools=action_tool_specs(),
        report_loader=ReportHolder(report).take,
        clock=lambda: NOW,
    )

    response = asyncio.run(service.run(_request()))

    assert response.proposal is None
    assert response.confidence is AnswerConfidence.LOW
    assert response.limitations
