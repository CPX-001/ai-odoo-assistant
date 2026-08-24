from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import UUID

import pytest

from odoo_ai.application.batch_command import BatchCommandError, BatchCommandService
from odoo_ai.application.batch_execution import BatchExecutionError
from odoo_ai.application.batch_jobs import BatchJobError
from odoo_ai.contracts.batch import (
    BatchDeleteItem,
    BatchItemResult,
    BatchItemState,
    BatchMutationKind,
    BatchMutationRequest,
    BatchMutationResult,
)
from odoo_ai.contracts.batch_job import (
    BatchCommandReceipt,
    BatchJobState,
    BatchMutationJobSnapshot,
    BatchMutationJobSpec,
)
from odoo_ai.contracts.chat import ChatActor
from odoo_ai.contracts.content_source import ContentSourceDescriptor
from odoo_ai.ports.batch_jobs import StoredBatchMutationJob

NOW = datetime(2026, 8, 25, 0, 0, tzinfo=UTC)
ACTOR = ChatActor(database="odoo-test", uid=7)
JOB_ID = UUID(int=1)
ATTEMPT_ID = UUID(int=2)
AUTHORIZATION_ID = UUID(int=3)
JOB_FINGERPRINT = "batch-job:v1:sha256:" + "a" * 64


def _stored() -> StoredBatchMutationJob:
    spec = BatchMutationJobSpec(
        actor=ACTOR,
        instance_id="instance-test",
        company_id=1,
        allowed_company_ids=(1,),
        operation=BatchMutationKind.DELETE,
        model="res.partner",
        policy_revision="agent-policy-v3",
        source=ContentSourceDescriptor(
            provider="odoo.attachment",
            reference="attachment:42",
            content_fingerprint="content:v1:sha256:" + "b" * 64,
        ),
    )
    return StoredBatchMutationJob(
        snapshot=BatchMutationJobSnapshot(
            job_id=JOB_ID,
            spec=spec,
            job_fingerprint=JOB_FINGERPRINT,
            state=BatchJobState.EXECUTING,
            item_count=1,
            applied_count=0,
            failed_count=0,
            attempt_id=ATTEMPT_ID,
            created_at=NOW,
            execution_started_at=NOW,
        ),
        items=(),
    )


def _request() -> BatchMutationRequest:
    return BatchMutationRequest(
        operation=BatchMutationKind.DELETE,
        model="res.partner",
        items=(BatchDeleteItem(source_ref="row:1", record_id=11),),
    )


def _result() -> BatchMutationResult:
    return BatchMutationResult(
        operation=BatchMutationKind.DELETE,
        model="res.partner",
        total_items=1,
        applied_items=1,
        failed_items=0,
        results=(
            BatchItemResult(
                source_ref="row:1",
                state=BatchItemState.APPLIED,
                record_id=11,
            ),
        ),
    )


def _receipt() -> BatchCommandReceipt:
    return BatchCommandReceipt(
        job_id=JOB_ID,
        attempt_id=ATTEMPT_ID,
        job_fingerprint=JOB_FINGERPRINT,
        state=BatchJobState.COMPLETED,
        total_items=1,
        applied_items=1,
        failed_items=0,
        completed_at=NOW,
    )


class FakeJobs:
    def __init__(self, *, finish_race=False) -> None:
        self.finish_race = finish_race
        self.terminal_calls = 0
        self.mark_unknown_calls = 0

    def terminal_receipt(self, job_id, *, actor, expected_fingerprint):
        assert job_id == JOB_ID
        assert actor == ACTOR
        assert expected_fingerprint == JOB_FINGERPRINT
        self.terminal_calls += 1
        if self.finish_race and self.terminal_calls > 1:
            return _receipt()
        return None

    def claim_execution(self, job_id, *, actor, expected_fingerprint):
        assert job_id == JOB_ID
        assert actor == ACTOR
        assert expected_fingerprint == JOB_FINGERPRINT
        return _stored()

    def execution_request(self, stored):
        assert stored.snapshot.attempt_id == ATTEMPT_ID
        return _request()

    def finish_execution(self, *, job_id, attempt_id, result, error_code=None):
        del error_code
        assert job_id == JOB_ID
        assert attempt_id == ATTEMPT_ID
        assert result == _result()
        if self.finish_race:
            raise BatchJobError("batch_job_invalid_state")
        return _receipt()

    def mark_execution_unknown(self, *, job_id, attempt_id, error_code):
        assert job_id == JOB_ID
        assert attempt_id == ATTEMPT_ID
        assert error_code == "batch_execution_outcome_unknown"
        self.mark_unknown_calls += 1
        return None


class FakeExecution:
    def __init__(self, *, fail=False) -> None:
        self.fail = fail
        self.context = None

    async def execute(self, request, *, context):
        assert request == _request()
        self.context = context
        if self.fail:
            raise BatchExecutionError("upstream_unavailable")
        return _result()


def test_plan_authorization_is_bound_into_batch_execution_context() -> None:
    jobs = FakeJobs()
    execution = FakeExecution()
    service = BatchCommandService(jobs=jobs, execution=execution)

    receipt = asyncio.run(
        service.execute(
            job_id=JOB_ID,
            expected_fingerprint=JOB_FINGERPRINT,
            actor=ACTOR,
            authorization_id=AUTHORIZATION_ID,
        )
    )

    assert receipt.state is BatchJobState.COMPLETED
    assert execution.context.authorization_id == AUTHORIZATION_ID
    assert execution.context.attempt_id == ATTEMPT_ID
    assert execution.context.job_fingerprint == JOB_FINGERPRINT


def test_concurrent_finish_returns_existing_terminal_receipt() -> None:
    jobs = FakeJobs(finish_race=True)
    service = BatchCommandService(jobs=jobs, execution=FakeExecution())

    receipt = asyncio.run(
        service.execute(
            job_id=JOB_ID,
            expected_fingerprint=JOB_FINGERPRINT,
            actor=ACTOR,
            authorization_id=AUTHORIZATION_ID,
        )
    )

    assert receipt == _receipt()
    assert jobs.terminal_calls == 2
    assert jobs.mark_unknown_calls == 0


def test_ambiguous_gateway_failure_preserves_attempt_as_unknown() -> None:
    jobs = FakeJobs()
    service = BatchCommandService(jobs=jobs, execution=FakeExecution(fail=True))

    with pytest.raises(BatchCommandError, match="batch_execution_outcome_unknown"):
        asyncio.run(
            service.execute(
                job_id=JOB_ID,
                expected_fingerprint=JOB_FINGERPRINT,
                actor=ACTOR,
                authorization_id=AUTHORIZATION_ID,
            )
        )

    assert jobs.mark_unknown_calls == 1
