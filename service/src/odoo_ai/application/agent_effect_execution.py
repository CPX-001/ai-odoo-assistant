"""Explicit execution strategies for host-authorized agent write steps."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from pydantic import ValidationError

from odoo_ai.application.action_command import ActionCommandService
from odoo_ai.application.batch_command import BatchCommandError, BatchCommandService
from odoo_ai.contracts import (
    ActionDecision,
    ActionDecisionCommandRequest,
    ActionProposalState,
    AgentPlanStep,
    OdooActionActorContext,
)
from odoo_ai.contracts.batch_job import BatchJobState, BatchProposalHandle
from odoo_ai.contracts.chat import ChatActor

BATCH_PREVIEW_TOOL_NAME = "odoo.preview_batch_mutation"


class AgentEffectExecutionError(RuntimeError):
    def __init__(self, code: str, status_code: int = 409) -> None:
        super().__init__(code)
        self.code = code
        self.status_code = status_code


@dataclass(frozen=True, slots=True)
class AgentStepExecutionResult:
    """Transport-neutral terminal outcome consumed by the plan state machine."""

    state: Literal["completed", "partial", "failed"]
    receipt: dict[str, object]
    error_code: str | None = None


class AgentWriteStepDispatcher:
    """Dispatch only the two explicitly supported immutable effect families."""

    def __init__(
        self,
        *,
        actions: ActionCommandService,
        batches: BatchCommandService | None = None,
    ) -> None:
        self._actions = actions
        self._batches = batches

    async def execute(
        self,
        step: AgentPlanStep,
        *,
        actor: ChatActor,
        company_id: int,
        allowed_company_ids: tuple[int, ...],
        authorization_id: UUID,
    ) -> AgentStepExecutionResult:
        if not step.is_write:
            raise AgentEffectExecutionError("agent_step_not_write", 503)
        if step.tool_name == BATCH_PREVIEW_TOOL_NAME:
            return await self._execute_batch(
                step,
                actor=actor,
                authorization_id=authorization_id,
            )
        return await self._execute_action(
            step,
            actor=actor,
            company_id=company_id,
            allowed_company_ids=allowed_company_ids,
        )

    async def _execute_action(
        self,
        step: AgentPlanStep,
        *,
        actor: ChatActor,
        company_id: int,
        allowed_company_ids: tuple[int, ...],
    ) -> AgentStepExecutionResult:
        if step.proposal_id is None or step.proposal_fingerprint is None:
            raise AgentEffectExecutionError("agent_step_proposal_missing", 503)
        receipt = await self._actions.decide_and_execute(
            ActionDecisionCommandRequest(
                proposal_id=step.proposal_id,
                decision=ActionDecision.APPROVE,
                actor=OdooActionActorContext(
                    database=actor.database,
                    uid=actor.uid,
                    company_id=company_id,
                    allowed_company_ids=allowed_company_ids,
                ),
            )
        )
        if receipt.payload_fingerprint != step.proposal_fingerprint:
            raise AgentEffectExecutionError("agent_step_receipt_mismatch", 503)
        successful = receipt.state is ActionProposalState.VERIFIED
        return AgentStepExecutionResult(
            state="completed" if successful else "failed",
            receipt=receipt.model_dump(mode="json"),
            error_code=receipt.error_code,
        )

    async def _execute_batch(
        self,
        step: AgentPlanStep,
        *,
        actor: ChatActor,
        authorization_id: UUID,
    ) -> AgentStepExecutionResult:
        if self._batches is None:
            raise AgentEffectExecutionError("batch_execution_unavailable", 503)
        if step.proposal_id is not None or step.proposal_fingerprint is not None:
            raise AgentEffectExecutionError("agent_batch_binding_invalid", 503)
        try:
            handle = BatchProposalHandle.model_validate(step.arguments)
        except ValidationError:
            raise AgentEffectExecutionError("agent_batch_binding_invalid", 503) from None
        if step.estimated_records != handle.item_count:
            raise AgentEffectExecutionError("agent_batch_binding_mismatch", 503)
        try:
            receipt = await self._batches.execute(
                job_id=handle.job_id,
                expected_fingerprint=handle.job_fingerprint,
                actor=actor,
                authorization_id=authorization_id,
            )
        except BatchCommandError as error:
            raise AgentEffectExecutionError(error.code, error.status_code) from None
        state = {
            BatchJobState.COMPLETED: "completed",
            BatchJobState.PARTIAL: "partial",
            BatchJobState.FAILED: "failed",
        }.get(receipt.state)
        if state is None:
            raise AgentEffectExecutionError("agent_batch_receipt_invalid", 503)
        return AgentStepExecutionResult(
            state=state,
            receipt=receipt.model_dump(mode="json"),
            error_code=receipt.error_code,
        )
