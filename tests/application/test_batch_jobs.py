from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID

import pytest
from pydantic import ValidationError

from odoo_ai.application.batch_jobs import (
    BatchJobError,
    BatchMutationJobService,
)
from odoo_ai.contracts.batch import (
    BatchDeleteItem,
    BatchItemResult,
    BatchItemState,
    BatchMutationKind,
    BatchMutationRequest,
    BatchMutationResult,
)
from odoo_ai.contracts.batch_job import (
    BatchJobState,
    BatchMutationJobSpec,
)
from odoo_ai.contracts.chat import ChatActor
from odoo_ai.contracts.content_source import ContentSourceDescriptor
from odoo_ai.ports.batch_jobs import (
    BatchJobTransitionOutcome,
    BatchJobTransitionResult,
    StoredBatchMutationJob,
)

NOW = datetime(2026, 8, 25, 0, 0, tzinfo=UTC)
ACTOR = ChatActor(database="odoo-test", uid=7)


def _source(reference: str = "attachment:42") -> ContentSourceDescriptor:
    return ContentSourceDescriptor(
        provider="odoo.attachment",
        reference=reference,
        display_name="Clientes.pdf",
        media_type="application/pdf",
        content_fingerprint="content:v1:sha256:" + "a" * 64,
    )


def _spec(*, source: ContentSourceDescriptor | None = None) -> BatchMutationJobSpec:
    return BatchMutationJobSpec(
        turn_id=UUID(int=100),
        conversation_id=UUID(int=101),
        actor=ACTOR,
        instance_id="instance-test",
        company_id=1,
        allowed_company_ids=(1,),
        operation=BatchMutationKind.DELETE,
        model="res.partner",
        policy_revision="agent-policy-v3",
        source=source or _source(),
    )


def _request() -> BatchMutationRequest:
    return BatchMutationRequest(
        operation=BatchMutationKind.DELETE,
        model="res.partner",
        items=(
            BatchDeleteItem(source_ref="pdf:page1:item1", record_id=11),
            BatchDeleteItem(source_ref="pdf:page1:item2", record_id=12),
            BatchDeleteItem(source_ref="pdf:page2:item1", record_id=13),
        ),
    )


class MemoryBatchJobStore:
    def __init__(self) -> None:
        self.jobs: dict[UUID, StoredBatchMutationJob] = {}

    def create(self, job: StoredBatchMutationJob) -> None:
        if job.snapshot.job_id in self.jobs:
            raise RuntimeError("duplicate")
        self.jobs[job.snapshot.job_id] = job

    def get(self, job_id: UUID):
        return self.jobs.get(job_id)

    def claim_execution(
        self,
        *,
        job_id,
        actor,
        expected_fingerprint,
        attempt_id,
        started_at,
    ):
        job = self.jobs.get(job_id)
        if job is None:
            return BatchJobTransitionResult(BatchJobTransitionOutcome.NOT_FOUND)
        if job.snapshot.spec.actor != actor:
            return BatchJobTransitionResult(BatchJobTransitionOutcome.BINDING_MISMATCH, job)
        if job.snapshot.job_fingerprint != expected_fingerprint:
            return BatchJobTransitionResult(BatchJobTransitionOutcome.FINGERPRINT_MISMATCH, job)
        if job.snapshot.state is BatchJobState.PREPARED:
            updated = StoredBatchMutationJob(
                snapshot=job.snapshot.model_copy(
                    update={
                        "state": BatchJobState.EXECUTING,
                        "attempt_id": attempt_id,
                        "execution_started_at": started_at,
                        "error_code": None,
                    }
                ),
                items=job.items,
            )
            self.jobs[job_id] = updated
            return BatchJobTransitionResult(BatchJobTransitionOutcome.APPLIED, updated)
        if job.snapshot.state in {
            BatchJobState.EXECUTING,
            BatchJobState.EXECUTION_UNKNOWN,
        }:
            updated = StoredBatchMutationJob(
                snapshot=job.snapshot.model_copy(
                    update={
                        "state": BatchJobState.EXECUTING,
                        "error_code": None,
                    }
                ),
                items=job.items,
            )
            self.jobs[job_id] = updated
            return BatchJobTransitionResult(BatchJobTransitionOutcome.RESUMED, updated)
        return BatchJobTransitionResult(BatchJobTransitionOutcome.INVALID_STATE, job)

    def mark_execution_unknown(
        self,
        *,
        job_id,
        attempt_id,
        occurred_at,
        error_code,
    ):
        del occurred_at
        job = self.jobs[job_id]
        if (
            job.snapshot.state is not BatchJobState.EXECUTING
            or job.snapshot.attempt_id != attempt_id
        ):
            raise RuntimeError("invalid_state")
        updated = StoredBatchMutationJob(
            snapshot=job.snapshot.model_copy(
                update={
                    "state": BatchJobState.EXECUTION_UNKNOWN,
                    "error_code": error_code,
                }
            ),
            items=job.items,
        )
        self.jobs[job_id] = updated
        return updated

    def finish_execution(
        self,
        *,
        job_id,
        attempt_id,
        result,
        completed_at,
        error_code=None,
    ):
        job = self.jobs[job_id]
        if (
            job.snapshot.state is not BatchJobState.EXECUTING
            or job.snapshot.attempt_id != attempt_id
        ):
            raise RuntimeError("invalid_state")
        results = {item.source_ref: item for item in result.results}
        items = tuple(
            item.model_copy(update={"result": results[item.item.source_ref]})
            for item in job.items
        )
        state = (
            BatchJobState.COMPLETED
            if result.failed_items == 0
            else BatchJobState.FAILED
            if result.applied_items == 0
            else BatchJobState.PARTIAL
        )
        updated = StoredBatchMutationJob(
            snapshot=job.snapshot.model_copy(
                update={
                    "state": state,
                    "applied_count": result.applied_items,
                    "failed_count": result.failed_items,
                    "completed_at": completed_at,
                    "error_code": error_code,
                }
            ),
            items=items,
        )
        self.jobs[job_id] = updated
        return updated


def _service(store: MemoryBatchJobStore, ids: list[UUID]) -> BatchMutationJobService:
    values = iter(ids)
    return BatchMutationJobService(
        store,
        clock=lambda: NOW,
        id_factory=lambda: next(values),
    )


def test_content_source_descriptor_is_transport_neutral_and_strict() -> None:
    source = _source()

    assert source.provider == "odoo.attachment"
    assert source.reference == "attachment:42"
    assert source.media_type == "application/pdf"

    with pytest.raises(ValidationError):
        ContentSourceDescriptor(
            provider="odoo.attachment",
            reference="attachment:42\nsecret",
        )
    with pytest.raises(ValidationError):
        ContentSourceDescriptor(
            provider="odoo.attachment",
            reference="attachment:42",
            media_type="Application/PDF",
        )


def test_job_handle_contains_no_row_payload_and_provenance_is_fingerprinted() -> None:
    first_store = MemoryBatchJobStore()
    second_store = MemoryBatchJobStore()
    job_id = UUID(int=1)
    first = _service(first_store, [job_id]).prepare(spec=_spec(), request=_request())
    second = _service(second_store, [job_id]).prepare(
        spec=_spec(source=_source("attachment:99")),
        request=_request(),
    )

    assert first.item_count == 3
    assert first.source_provider == "odoo.attachment"
    assert "items" not in first.model_dump(mode="json")
    assert first.job_fingerprint != second.job_fingerprint


def test_tampered_persisted_row_is_rejected_before_authority_use() -> None:
    store = MemoryBatchJobStore()
    service = _service(store, [UUID(int=2)])
    handle = service.prepare(spec=_spec(), request=_request())
    original = store.jobs[handle.job_id]
    corrupted_item = original.items[0].model_copy(
        update={
            "item": BatchDeleteItem(
                source_ref=original.items[0].item.source_ref,
                record_id=999,
            )
        }
    )
    store.jobs[handle.job_id] = replace(
        original,
        items=(corrupted_item, *original.items[1:]),
    )

    with pytest.raises(BatchJobError, match="batch_job_corrupt"):
        service.get_bound(
            handle.job_id,
            actor=ACTOR,
            expected_fingerprint=handle.job_fingerprint,
        )


def test_execution_unknown_resumes_with_original_attempt_id() -> None:
    store = MemoryBatchJobStore()
    job_id = UUID(int=3)
    first_attempt = UUID(int=4)
    discarded_resume_candidate = UUID(int=5)
    service = _service(store, [job_id, first_attempt, discarded_resume_candidate])
    handle = service.prepare(spec=_spec(), request=_request())

    claimed = service.claim_execution(
        handle.job_id,
        actor=ACTOR,
        expected_fingerprint=handle.job_fingerprint,
    )
    assert claimed.snapshot.attempt_id == first_attempt

    unknown = service.mark_execution_unknown(
        job_id=handle.job_id,
        attempt_id=first_attempt,
        error_code="batch_execution_outcome_unknown",
    )
    assert unknown.snapshot.state is BatchJobState.EXECUTION_UNKNOWN

    resumed = service.claim_execution(
        handle.job_id,
        actor=ACTOR,
        expected_fingerprint=handle.job_fingerprint,
    )
    assert resumed.snapshot.state is BatchJobState.EXECUTING
    assert resumed.snapshot.attempt_id == first_attempt
    assert resumed.snapshot.attempt_id != discarded_resume_candidate


def test_persisted_executing_job_reclaims_original_attempt_after_assistant_crash() -> None:
    store = MemoryBatchJobStore()
    job_id = UUID(int=9)
    original_attempt = UUID(int=10)
    discarded_recovery_candidate = UUID(int=11)
    service = _service(
        store,
        [job_id, original_attempt, discarded_recovery_candidate],
    )
    handle = service.prepare(spec=_spec(), request=_request())
    first = service.claim_execution(
        handle.job_id,
        actor=ACTOR,
        expected_fingerprint=handle.job_fingerprint,
    )
    assert first.snapshot.state is BatchJobState.EXECUTING
    assert first.snapshot.attempt_id == original_attempt

    recovered = service.claim_execution(
        handle.job_id,
        actor=ACTOR,
        expected_fingerprint=handle.job_fingerprint,
    )

    assert recovered.snapshot.state is BatchJobState.EXECUTING
    assert recovered.snapshot.attempt_id == original_attempt
    assert recovered.snapshot.attempt_id != discarded_recovery_candidate


def test_partial_result_is_durable_and_compact_receipt_lists_failed_sources() -> None:
    store = MemoryBatchJobStore()
    job_id = UUID(int=6)
    attempt_id = UUID(int=7)
    service = _service(store, [job_id, attempt_id])
    handle = service.prepare(spec=_spec(), request=_request())
    claimed = service.claim_execution(
        handle.job_id,
        actor=ACTOR,
        expected_fingerprint=handle.job_fingerprint,
    )
    request = service.execution_request(claimed)
    result = BatchMutationResult(
        operation=request.operation,
        model=request.model,
        total_items=3,
        applied_items=2,
        failed_items=1,
        results=(
            BatchItemResult(
                source_ref="pdf:page1:item1",
                state=BatchItemState.APPLIED,
                record_id=11,
            ),
            BatchItemResult(
                source_ref="pdf:page1:item2",
                state=BatchItemState.FAILED,
                error_code="business_rule_rejected",
            ),
            BatchItemResult(
                source_ref="pdf:page2:item1",
                state=BatchItemState.APPLIED,
                record_id=13,
            ),
        ),
    )

    receipt = service.finish_execution(
        job_id=job_id,
        attempt_id=attempt_id,
        result=result,
    )

    assert receipt.state is BatchJobState.PARTIAL
    assert receipt.applied_items == 2
    assert receipt.failed_items == 1
    assert receipt.failed_source_refs == ("pdf:page1:item2",)
    assert "results" not in receipt.model_dump(mode="json")


def test_actor_and_fingerprint_are_checked_before_loading_execution_payload() -> None:
    store = MemoryBatchJobStore()
    service = _service(store, [UUID(int=8)])
    handle = service.prepare(spec=_spec(), request=_request())

    with pytest.raises(BatchJobError, match="batch_job_binding_mismatch"):
        service.get_bound(
            handle.job_id,
            actor=ChatActor(database="odoo-test", uid=99),
            expected_fingerprint=handle.job_fingerprint,
        )
    with pytest.raises(BatchJobError, match="batch_job_fingerprint_mismatch"):
        service.get_bound(
            handle.job_id,
            actor=ACTOR,
            expected_fingerprint="batch-job:v1:sha256:" + "f" * 64,
        )
