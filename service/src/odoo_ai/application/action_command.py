"""Deterministic ACTION decision and execution operation outside reasoning."""

from __future__ import annotations

import asyncio
from typing import cast

from odoo_ai.application.action_approval import ActionApprovalService
from odoo_ai.application.action_execution import ActionExecutionService
from odoo_ai.contracts import (
    ActionCommandReceipt,
    ActionDecision,
    ActionDecisionCommandRequest,
    ActionDecisionRequest,
    ActionProposalState,
    ExecuteApprovedActionRequest,
)


class ActionCommandService:
    """Persist an explicit decision and execute only the stored approved payload."""

    def __init__(
        self,
        *,
        approvals: ActionApprovalService,
        executions: ActionExecutionService,
    ) -> None:
        self._approvals = approvals
        self._executions = executions

    async def decide_and_execute(
        self, request: ActionDecisionCommandRequest
    ) -> ActionCommandReceipt:
        actor = await asyncio.to_thread(
            self._approvals.bind_odoo_actor,
            proposal_id=request.proposal_id,
            actor=request.actor,
        )
        decision = await asyncio.to_thread(
            self._approvals.decide,
            ActionDecisionRequest(
                proposal_id=request.proposal_id,
                decision=request.decision,
                actor=actor,
            ),
        )
        if request.decision is ActionDecision.REJECT:
            return ActionCommandReceipt(
                proposal_id=decision.proposal_id,
                state=ActionProposalState.REJECTED,
                payload_fingerprint=decision.payload_fingerprint,
                completed_at=decision.decided_at,
            )
        if decision.approval_id is None:
            raise RuntimeError("approval_store_corrupt")
        execution = await self._executions.execute(
            ExecuteApprovedActionRequest(
                approval_id=decision.approval_id,
                actor=actor,
            )
        )
        pointer = (
            execution.evidence.pointer
            if execution.evidence is not None and execution.evidence.pointer is not None
            else {}
        )
        raw_record_model = pointer.get("model")
        raw_record_id = pointer.get("record_id")
        has_record_pointer = isinstance(raw_record_model, str) and isinstance(
            raw_record_id, int
        ) and not isinstance(raw_record_id, bool)
        record_model = cast(str, raw_record_model) if has_record_pointer else None
        record_id: int | None = raw_record_id if has_record_pointer else None  # type: ignore[assignment]
        return ActionCommandReceipt(
            proposal_id=execution.proposal_id,
            state=execution.state,
            payload_fingerprint=execution.payload_fingerprint,
            completed_at=execution.completed_at,
            approval_id=execution.approval_id,
            attempt_id=execution.attempt_id,
            evidence_id=execution.evidence_id,
            record_model=record_model,
            record_id=record_id,
            error_code=execution.error_code,
        )
