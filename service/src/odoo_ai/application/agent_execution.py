"""Execute only a previously host-authorized immutable agent plan."""

from __future__ import annotations

import asyncio
from uuid import UUID

from odoo_ai.application.action_approval import ActionApprovalError
from odoo_ai.application.action_command import ActionCommandService
from odoo_ai.application.action_execution import ActionExecutionError
from odoo_ai.application.agent_plans import AgentPlanError, AgentPlanService
from odoo_ai.contracts import (
    ActionDecision,
    ActionDecisionCommandRequest,
    ActionProposalState,
    AgentPlanExecutionRequest,
    AgentPlanStatusResponse,
    OdooActionActorContext,
    PlanState,
)


class AgentExecutionError(RuntimeError):
    def __init__(self, code: str, status_code: int = 409) -> None:
        super().__init__(code)
        self.code = code
        self.status_code = status_code


class AgentPlanExecutionService:
    """Translate one grouped host authorization into exact proposal executions."""

    def __init__(
        self,
        *,
        plans: AgentPlanService,
        actions: ActionCommandService,
    ) -> None:
        self._plans = plans
        self._actions = actions

    async def execute(
        self,
        request: AgentPlanExecutionRequest,
    ) -> AgentPlanStatusResponse:
        try:
            plan = await asyncio.to_thread(self._plans.claim_execution, request)
            actor = OdooActionActorContext(
                database=plan.actor.database,
                uid=plan.actor.uid,
                company_id=plan.company_id,
                allowed_company_ids=plan.allowed_company_ids,
            )
            completed = 0
            for position, step in enumerate(plan.steps):
                if not step.is_write:
                    continue
                if step.proposal_id is None or step.proposal_fingerprint is None:
                    raise AgentExecutionError("agent_step_proposal_missing", 503)
                receipt = await self._actions.decide_and_execute(
                    ActionDecisionCommandRequest(
                        proposal_id=step.proposal_id,
                        decision=ActionDecision.APPROVE,
                        actor=actor,
                    )
                )
                if receipt.payload_fingerprint != step.proposal_fingerprint:
                    raise AgentExecutionError("agent_step_receipt_mismatch", 503)
                successful = receipt.state is ActionProposalState.VERIFIED
                await asyncio.to_thread(
                    self._plans.record_step_result,
                    plan_id=plan.plan_id,
                    step_id=step.step_id,
                    state="completed" if successful else "failed",
                    receipt=receipt.model_dump(mode="json"),
                    error_code=receipt.error_code,
                )
                if not successful:
                    for skipped in plan.steps[position + 1 :]:
                        if skipped.is_write:
                            await asyncio.to_thread(
                                self._plans.record_step_result,
                                plan_id=plan.plan_id,
                                step_id=skipped.step_id,
                                state="skipped",
                                error_code="dependency_failed",
                            )
                    terminal = PlanState.PARTIAL if completed else PlanState.FAILED
                    await asyncio.to_thread(
                        self._plans.complete,
                        plan_id=plan.plan_id,
                        state=terminal,
                        error_code=receipt.error_code or "agent_step_failed",
                    )
                    return await asyncio.to_thread(
                        self._plans.get_status,
                        plan.plan_id,
                        plan.actor.database,
                        plan.actor.uid,
                    )
                completed += 1
            await asyncio.to_thread(
                self._plans.complete,
                plan_id=plan.plan_id,
                state=PlanState.COMPLETED,
            )
            return await asyncio.to_thread(
                self._plans.get_status,
                plan.plan_id,
                plan.actor.database,
                plan.actor.uid,
            )
        except AgentExecutionError:
            raise
        except AgentPlanError as error:
            raise AgentExecutionError(error.code, error.status_code) from None
        except ActionApprovalError as error:
            await self._fail_claimed_plan(request.plan_id, error.code)
            raise AgentExecutionError(error.code, error.status_code) from None
        except ActionExecutionError as error:
            await self._fail_claimed_plan(request.plan_id, error.code)
            raise AgentExecutionError(error.code, error.status_code) from None
        except Exception:
            await self._fail_claimed_plan(request.plan_id, "agent_execution_unavailable")
            raise AgentExecutionError("agent_execution_unavailable", 503) from None

    async def _fail_claimed_plan(self, plan_id: UUID, error_code: str) -> None:
        try:
            await asyncio.to_thread(
                self._plans.complete,
                plan_id=plan_id,
                state=PlanState.FAILED,
                error_code=error_code,
            )
        except Exception:
            pass
