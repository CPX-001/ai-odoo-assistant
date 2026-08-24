from uuid import UUID

from odoo_ai.adapters.agent_tools import _ordered_preview_traces
from odoo_ai.contracts import ActionProposalTrace
from odoo_ai.contracts.batch_job import BatchProposalTrace
from odoo_ai.contracts.tool_execution import ToolExecutionEvent


def _event(tool_name: str) -> ToolExecutionEvent:
    return ToolExecutionEvent(
        event_name="tool.completed",
        status="ok",
        attributes={"tool_name": tool_name},
    )


def test_empty_batch_preview_does_not_consume_later_batch_trace() -> None:
    action = ActionProposalTrace(
        tool_name="odoo.preview_record_create",
        arguments={"model": "res.partner"},
        proposal_id=UUID(int=51),
        payload_fingerprint="action-payload:v1:sha256:" + "a" * 64,
    )
    batch = BatchProposalTrace(
        tool_name="odoo.preview_batch_mutation",
        arguments={"job_id": "opaque"},
        job_id=UUID(int=52),
        job_fingerprint="batch-job:v1:sha256:" + "b" * 64,
    )
    events = (
        _event("odoo.preview_batch_mutation"),
        _event("odoo.preview_record_create"),
        _event("odoo.preview_batch_mutation"),
    )

    ordered = _ordered_preview_traces(
        events,
        (action,),
        (None, batch),
    )

    assert ordered == (action, batch)
