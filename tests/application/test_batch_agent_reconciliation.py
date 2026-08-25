from __future__ import annotations

from uuid import UUID

import pytest
from odoo_ai.application.agent_turn import AgentTurnError, _reconcile_previews
from odoo_ai.contracts import ActionToolReport, AgentCandidateOutput, AgentCandidateStep
from odoo_ai.contracts.batch import BatchFailureMode, BatchMutationKind
from odoo_ai.contracts.batch_job import BatchProposalHandle, BatchProposalTrace

TURN_ID = UUID(int=31)
JOB_ID = UUID(int=32)
JOB_FINGERPRINT = "batch-job:v1:sha256:" + "c" * 64


def _handle() -> BatchProposalHandle:
    return BatchProposalHandle(
        job_id=JOB_ID,
        turn_id=TURN_ID,
        job_fingerprint=JOB_FINGERPRINT,
        operation=BatchMutationKind.CREATE,
        model="res.partner",
        item_count=73,
        failure_mode=BatchFailureMode.CONTINUE_ON_ERROR,
        source_provider="agent.turn",
        source_display_name="Agent turn batch",
    )


def _candidate() -> AgentCandidateOutput:
    return AgentCandidateOutput(
        answer_markdown="Prepararé los contactos.",
        confidence="high",
        steps=(
            AgentCandidateStep(
                step_id="bulk",
                title="Crear contactos",
                tool_name="odoo.preview_batch_mutation",
                arguments={"item_count": 1, "job_id": "inventado"},
            ),
        ),
    )


def test_reconciliation_replaces_model_arguments_with_host_sealed_handle() -> None:
    handle = _handle()
    trace = BatchProposalTrace(
        tool_name="odoo.preview_batch_mutation",
        arguments=handle.model_dump(mode="json"),
        job_id=handle.job_id,
        job_fingerprint=handle.job_fingerprint,
    )
    report = ActionToolReport(
        batch_traces=(trace,),
        preview_traces=(trace,),
    )

    candidate, bindings = _reconcile_previews(
        _candidate(),
        report,
        turn_id=TURN_ID,
    )

    assert candidate.steps[0].arguments == handle.model_dump(mode="json")
    assert candidate.steps[0].arguments["item_count"] == 73
    assert bindings["bulk"].estimated_records == 73
    assert bindings["bulk"].proposal_id is None


def test_reconciliation_rejects_trace_fingerprint_tampering() -> None:
    handle = _handle()
    trace = BatchProposalTrace(
        tool_name="odoo.preview_batch_mutation",
        arguments=handle.model_dump(mode="json"),
        job_id=handle.job_id,
        job_fingerprint="batch-job:v1:sha256:" + "d" * 64,
    )
    report = ActionToolReport(
        batch_traces=(trace,),
        preview_traces=(trace,),
    )

    with pytest.raises(AgentTurnError, match="agent_preview_report_corrupt"):
        _reconcile_previews(_candidate(), report, turn_id=TURN_ID)


def test_reconciliation_rejects_handle_from_another_turn() -> None:
    handle = _handle().model_copy(update={"turn_id": UUID(int=99)})
    trace = BatchProposalTrace(
        tool_name="odoo.preview_batch_mutation",
        arguments=handle.model_dump(mode="json"),
        job_id=handle.job_id,
        job_fingerprint=handle.job_fingerprint,
    )
    report = ActionToolReport(
        batch_traces=(trace,),
        preview_traces=(trace,),
    )

    with pytest.raises(AgentTurnError, match="agent_preview_report_corrupt"):
        _reconcile_previews(_candidate(), report, turn_id=TURN_ID)
