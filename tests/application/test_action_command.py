import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID

from odoo_ai.application import ActionCommandService
from odoo_ai.contracts import (
    ActionActorContext,
    ActionCommandReceipt,
    ActionDecision,
    ActionDecisionCommandRequest,
    ActionDecisionReceipt,
    ActionExecutionReceipt,
    ActionProposalState,
    OdooActionActorContext,
)

NOW = datetime(2026, 8, 23, 12, 0, tzinfo=UTC)
PROPOSAL_ID = UUID("80000000-0000-4000-8000-000000000008")
APPROVAL_ID = UUID("90000000-0000-4000-8000-000000000009")
ATTEMPT_ID = UUID("a0000000-0000-4000-8000-00000000000a")
EVIDENCE_ID = UUID("b0000000-0000-4000-8000-00000000000b")
FINGERPRINT = "action-payload:v1:sha256:" + "c" * 64


class FakeApprovals:
    def __init__(self) -> None:
        self.decisions = []

    def bind_odoo_actor(self, *, proposal_id, actor):
        assert proposal_id == PROPOSAL_ID
        assert actor.uid == 17
        return ActionActorContext(
            instance_id="fixture-instance",
            database="fixture-db",
            uid=17,
            company_id=3,
            allowed_company_ids=(3,),
        )

    def decide(self, request):
        self.decisions.append(request)
        approved = request.decision is ActionDecision.APPROVE
        return ActionDecisionReceipt(
            proposal_id=PROPOSAL_ID,
            approval_id=APPROVAL_ID if approved else None,
            state=(
                ActionProposalState.APPROVED
                if approved
                else ActionProposalState.REJECTED
            ),
            payload_fingerprint=FINGERPRINT,
            decided_by_uid=17,
            decided_at=NOW,
            expires_at=NOW + timedelta(minutes=2),
        )


class FakeExecutions:
    def __init__(self) -> None:
        self.calls = []

    async def execute(self, request):
        self.calls.append(request)
        return ActionExecutionReceipt(
            proposal_id=PROPOSAL_ID,
            approval_id=APPROVAL_ID,
            attempt_id=ATTEMPT_ID,
            state=ActionProposalState.VERIFIED,
            payload_fingerprint=FINGERPRINT,
            completed_at=NOW,
            evidence_id=EVIDENCE_ID,
        )


def _request(decision: ActionDecision) -> ActionDecisionCommandRequest:
    return ActionDecisionCommandRequest(
        proposal_id=PROPOSAL_ID,
        decision=decision,
        actor=OdooActionActorContext(
            database="fixture-db",
            uid=17,
            company_id=3,
            allowed_company_ids=(3,),
        ),
    )


def test_approve_executes_stored_payload_without_reasoning_engine() -> None:
    approvals = FakeApprovals()
    executions = FakeExecutions()
    service = ActionCommandService(
        approvals=approvals,  # type: ignore[arg-type]
        executions=executions,  # type: ignore[arg-type]
    )

    receipt = asyncio.run(service.decide_and_execute(_request(ActionDecision.APPROVE)))

    assert isinstance(receipt, ActionCommandReceipt)
    assert receipt.state is ActionProposalState.VERIFIED
    assert receipt.evidence_id == EVIDENCE_ID
    assert len(approvals.decisions) == 1
    assert len(executions.calls) == 1
    assert not hasattr(service, "reasoning_engine")


def test_reject_is_terminal_and_never_calls_execution() -> None:
    approvals = FakeApprovals()
    executions = FakeExecutions()
    service = ActionCommandService(
        approvals=approvals,  # type: ignore[arg-type]
        executions=executions,  # type: ignore[arg-type]
    )

    receipt = asyncio.run(service.decide_and_execute(_request(ActionDecision.REJECT)))

    assert receipt.state is ActionProposalState.REJECTED
    assert receipt.approval_id is None
    assert executions.calls == []
