from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID

from odoo_ai.application.agent_execution import AgentPlanExecutionService
from odoo_ai.contracts import (
    AgentPlanExecutionRequest,
    AgentPlanStep,
    EffectScope,
    RiskLevel,
)
from odoo_ai.contracts.batch import BatchFailureMode, BatchMutationKind
from odoo_ai.contracts.batch_job import (
    BatchCommandReceipt,
    BatchJobState,
    BatchProposalHandle,
)
from odoo_ai.contracts.chat import ChatActor

NOW = datetime(2026, 8, 25, 1, 0, tzinfo=UTC)
ACTOR = ChatActor(database="odoo-test", uid=7)
PLAN_ID = UUID(int=41)
AUTHORIZATION_ID = UUID(int=42)
JOB_FINGERPRINT = "batch-job:v1:sha256:" + "a" * 64


def _batch_step(step_id: str, job_id: UUID, count: int) -> AgentPlanStep:
    handle = BatchProposalHandle(
        job_id=job_id,
        turn_id=UUID(int=40),
        job_fingerprint=JOB_FINGERPRINT,
        operation=BatchMutationKind.CREATE,
        model="res.partner",
        item_count=count,
        failure_mode=BatchFailureMode.CONTINUE_ON_ERROR,
        source_provider="agent.turn",
        source_display_name="Agent turn batch",
    )
    return AgentPlanStep(
        step_id=step_id,
        title="Crear contactos",
        tool_name="odoo.preview_batch_mutation",
        arguments=handle.model_dump(mode="json"),
        risk=RiskLevel.MODERATE,
        effect_scope=EffectScope.INTERNAL_REVERSIBLE,
        is_write=True,
        is_business_action=False,
        atomic=False,
        estimated_records=count,
        payload_fingerprint="agent-step:v1:sha256:" + "b" * 64,
    )


class FakePlans:
    def __init__(self) -> None:
        self.step_results = []
        self.completed = []
        self.status = object()
        self.plan = SimpleNamespace(
            plan_id=PLAN_ID,
            authorization_id=AUTHORIZATION_ID,
            actor=ACTOR,
            company_id=1,
            allowed_company_ids=(1,),
            steps=(
                _batch_step("bulk_first", UUID(int=43), 3),
                _batch_step("bulk_second", UUID(int=44), 2),
            ),
        )

    def claim_execution(self, request):
        assert request.plan_id == PLAN_ID
        return self.plan

    def record_step_result(self, **kwargs):
        self.step_results.append(kwargs)

    def complete(self, **kwargs):
        self.completed.append(kwargs)
        return self.plan

    def get_status(self, plan_id, database, uid):
        assert (plan_id, database, uid) == (PLAN_ID, "odoo-test", 7)
        return self.status


class NeverActions:
    async def decide_and_execute(self, request):
        raise AssertionError("ACTION path must not run")


class PartialBatchCommands:
    def __init__(self) -> None:
        self.calls = []

    async def execute(self, *, job_id, expected_fingerprint, actor, authorization_id):
        self.calls.append((job_id, expected_fingerprint, actor, authorization_id))
        return BatchCommandReceipt(
            job_id=job_id,
            attempt_id=UUID(int=45),
            job_fingerprint=expected_fingerprint,
            state=BatchJobState.PARTIAL,
            total_items=3,
            applied_items=2,
            failed_items=1,
            failed_source_refs=("row:2",),
            completed_at=NOW,
        )


def test_partial_batch_step_makes_plan_partial_and_skips_later_writes() -> None:
    plans = FakePlans()
    batches = PartialBatchCommands()
    service = AgentPlanExecutionService(
        plans=plans,
        actions=NeverActions(),
        batches=batches,
    )

    result = asyncio.run(
        service.execute(AgentPlanExecutionRequest(plan_id=PLAN_ID, actor=ACTOR))
    )

    assert result is plans.status
    assert len(batches.calls) == 1
    assert plans.step_results[0]["step_id"] == "bulk_first"
    assert plans.step_results[0]["state"] == "partial"
    assert plans.step_results[0]["receipt"]["state"] == "partial"
    assert plans.step_results[1] == {
        "plan_id": PLAN_ID,
        "step_id": "bulk_second",
        "state": "skipped",
        "error_code": "dependency_failed",
    }
    assert plans.completed == [
        {
            "plan_id": PLAN_ID,
            "state": "partial",
            "error_code": "agent_step_partial",
        }
    ]
