"""Execute only a previously host-authorized immutable agent plan."""

from __future__ import annotations

import asyncio
from uuid import UUID

from odoo_ai.application.action_approval import ActionApprovalError
from odoo_ai.application.action_command import ActionCommandService
from odoo_ai.application.action_execution import ActionExecutionError
from odoo_ai.application.agent_effect_execution import (
    BATCH_PREVIEW_TOOL_NAME,
    AgentEffectExecutionError,
    AgentStepExecutionResult,
    AgentWriteStepDispatcher,
)
from odoo_ai.application.agent_plans import (
    RECOVERABLE_EXECUTION_ERROR,
    AgentPlanError,
    AgentPlanService,
)
from odoo_ai.application.batch_command import BatchCommandService
from odoo_ai.contracts import (
    AgentPlanExecutionRequest,
    AgentPlanStatusResponse,
    AgentPlanStep,
    PlanState,
)
from odoo_ai.contracts.chat import ChatActor
from odoo_ai.ports.agent_plans import StoredAgentPlan


class AgentExecutionError(RuntimeError):
    def __init__(self, code: str, status_code: int = 409) -> None:
        super().__init__(code)
        self.code = code
        self.status_code = status_code


class AgentPlanExecutionService:
    """Translate one grouped host authorization into exact effect executions."""

    def __init__(
        self,
        *,
        plans: AgentPlanService,
        actions: ActionCommandService,
        batches: BatchCommandService | None = None,
    ) -> None:
        self._plans = plans
        self._effects = AgentWriteStepDispatcher(actions=actions, batches=batches)

    async def execute(
        self,
        request: AgentPlanExecutionRequest,
    ) -> AgentPlanStatusResponse:
        try:
            plan = await asyncio.to_thread(self._plans.claim_execution, request)
            if plan.authorization_id is None:
                raise AgentExecutionError("agent_plan_authorization_missing", 503)
            prior_results = {
                item.step_id: item for item in getattr(plan, "step_results", ())
            }
            completed = 0
            for position, step in enumerate(plan.steps):
                if not step.is_write:
                    continue
                prior = prior_results.get(step.step_id)
                if prior is not None:
                    if prior.state == "completed":
                        completed += 1
                        continue
                    if prior.state not in {"planned", "previewed"}:
                        raise AgentExecutionError("agent_plan_step_invalid_state", 503)
                try:
                    result = await self._execute_effect_with_recovery_retry(
                        step,
                        actor=plan.actor,
                        company_id=plan.company_id,
                        allowed_company_ids=plan.allowed_company_ids,
                        authorization_id=plan.authorization_id,
                    )
                except AgentEffectExecutionError as error:
                    if (
                        step.tool_name == BATCH_PREVIEW_TOOL_NAME
                        and error.code == RECOVERABLE_EXECUTION_ERROR
                    ):
                        await asyncio.to_thread(
                            self._plans.prepare_execution_recovery,
                            plan_id=plan.plan_id,
                            error_code=error.code,
                        )
                        return await asyncio.to_thread(
                            self._plans.get_status,
                            plan.plan_id,
                            plan.actor.database,
                            plan.actor.uid,
                        )
                    raise
                await asyncio.to_thread(
                    self._plans.record_step_result,
                    plan_id=plan.plan_id,
                    step_id=step.step_id,
                    state=result.state,
                    receipt=result.receipt,
                    error_code=result.error_code,
                )
                if result.state == "completed":
                    completed += 1
                    continue

                await self._skip_later_writes(plan, position)
                if result.state == "partial":
                    terminal = PlanState.PARTIAL
                    terminal_error = result.error_code or "agent_step_partial"
                else:
                    terminal = PlanState.PARTIAL if completed else PlanState.FAILED
                    terminal_error = result.error_code or "agent_step_failed"
                await asyncio.to_thread(
                    self._plans.complete,
                    plan_id=plan.plan_id,
                    state=terminal,
                    error_code=terminal_error,
                )
                return await asyncio.to_thread(
                    self._plans.get_status,
                    plan.plan_id,
                    plan.actor.database,
                    plan.actor.uid,
                )

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
        except AgentEffectExecutionError as error:
            await self._fail_claimed_plan(request.plan_id, error.code)
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

    async def _execute_effect_with_recovery_retry(
        self,
        step: AgentPlanStep,
        *,
        actor: ChatActor,
        company_id: int,
        allowed_company_ids: tuple[int, ...],
        authorization_id: UUID,
    ) -> AgentStepExecutionResult:
        try:
            return await self._effects.execute(
                step,
                actor=actor,
                company_id=company_id,
                allowed_company_ids=allowed_company_ids,
                authorization_id=authorization_id,
            )
        except AgentEffectExecutionError as error:
            if (
                step.tool_name != BATCH_PREVIEW_TOOL_NAME
                or error.code != RECOVERABLE_EXECUTION_ERROR
            ):
                raise
        # The batch job and Odoo receipts preserve the original attempt id. One
        # immediate retry therefore recovers a dropped response without minting new
        # authority or duplicating a successful create/patch/delete.
        return await self._effects.execute(
            step,
            actor=actor,
            company_id=company_id,
            allowed_company_ids=allowed_company_ids,
            authorization_id=authorization_id,
        )

    async def _skip_later_writes(self, plan: StoredAgentPlan, position: int) -> None:
        for skipped in plan.steps[position + 1 :]:
            if skipped.is_write:
                await asyncio.to_thread(
                    self._plans.record_step_result,
                    plan_id=plan.plan_id,
                    step_id=skipped.step_id,
                    state="skipped",
                    error_code="dependency_failed",
                )

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
