"""Host-owned lifecycle for immutable execution-ready batch jobs."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

from odoo_ai.contracts.action import Fingerprint
from odoo_ai.contracts.batch import (
    BatchItemResult,
    BatchMutationRequest,
    BatchMutationResult,
)
from odoo_ai.contracts.batch_job import (
    MAX_BATCH_FAILURE_PREVIEW,
    BatchCommandReceipt,
    BatchJobState,
    BatchMutationJobItem,
    BatchMutationJobSnapshot,
    BatchMutationJobSpec,
    BatchProposalHandle,
)
from odoo_ai.contracts.chat import ChatActor
from odoo_ai.ports.batch_jobs import (
    BatchJobTransitionOutcome,
    BatchMutationJobStore,
    StoredBatchMutationJob,
)

Clock = Callable[[], datetime]


class BatchJobError(RuntimeError):
    def __init__(self, code: str, status_code: int = 409) -> None:
        super().__init__(code)
        self.code = code
        self.status_code = status_code


class BatchMutationJobService:
    """Seal normalized rows once and verify them whenever authority is exercised."""

    def __init__(
        self,
        store: BatchMutationJobStore,
        *,
        clock: Clock = lambda: datetime.now(UTC),
        id_factory: Callable[[], UUID] = uuid4,
    ) -> None:
        self._store = store
        self._clock = clock
        self._id_factory = id_factory

    def prepare(
        self,
        *,
        spec: BatchMutationJobSpec,
        request: BatchMutationRequest,
    ) -> BatchProposalHandle:
        _require_request_matches_spec(request, spec)
        job_id = self._new_id()
        items = tuple(
            BatchMutationJobItem(
                position=position,
                item=item,
                item_fingerprint=batch_item_fingerprint(item),
            )
            for position, item in enumerate(request.items)
        )
        fingerprint = batch_job_fingerprint(job_id, spec, items)
        now = self._now()
        snapshot = BatchMutationJobSnapshot(
            job_id=job_id,
            spec=spec,
            job_fingerprint=fingerprint,
            state=BatchJobState.PREPARED,
            item_count=len(items),
            applied_count=0,
            failed_count=0,
            created_at=now,
        )
        stored = StoredBatchMutationJob(snapshot=snapshot, items=items)
        _verify_job(stored)
        try:
            self._store.create(stored)
        except Exception as error:
            code = str(getattr(error, "code", "batch_job_store_unavailable"))
            raise BatchJobError(code, 503) from None
        return _proposal_handle(snapshot)

    def get_bound(
        self,
        job_id: UUID,
        *,
        actor: ChatActor,
        expected_fingerprint: str,
    ) -> StoredBatchMutationJob:
        try:
            stored = self._store.get(job_id)
        except Exception:
            raise BatchJobError("batch_job_store_unavailable", 503) from None
        if stored is None:
            raise BatchJobError("batch_job_not_found", 404)
        _verify_job(stored)
        if stored.snapshot.spec.actor != actor:
            raise BatchJobError("batch_job_binding_mismatch", 403)
        if not _constant_time_equal(stored.snapshot.job_fingerprint, expected_fingerprint):
            raise BatchJobError("batch_job_fingerprint_mismatch", 409)
        return stored

    def claim_execution(
        self,
        job_id: UUID,
        *,
        actor: ChatActor,
        expected_fingerprint: str,
    ) -> StoredBatchMutationJob:
        proposed_attempt = self._new_id()
        try:
            transition = self._store.claim_execution(
                job_id=job_id,
                actor=actor,
                expected_fingerprint=expected_fingerprint,
                attempt_id=proposed_attempt,
                started_at=self._now(),
            )
        except Exception:
            raise BatchJobError("batch_job_store_unavailable", 503) from None
        stored = _transition_job(transition.outcome, transition.job)
        _verify_job(stored)
        if stored.snapshot.state is not BatchJobState.EXECUTING:
            raise BatchJobError("batch_job_invalid_state")
        if stored.snapshot.attempt_id is None:
            raise BatchJobError("batch_job_corrupt", 503)
        if transition.outcome is BatchJobTransitionOutcome.APPLIED:
            if stored.snapshot.attempt_id != proposed_attempt:
                raise BatchJobError("batch_job_corrupt", 503)
        elif transition.outcome is BatchJobTransitionOutcome.RESUMED:
            # The store deliberately preserves the old attempt id. Odoo therefore sees
            # the same idempotency identity after an ambiguous prior outcome.
            if stored.snapshot.attempt_id == proposed_attempt:
                raise BatchJobError("batch_job_corrupt", 503)
        return stored

    def execution_request(self, stored: StoredBatchMutationJob) -> BatchMutationRequest:
        _verify_job(stored)
        snapshot = stored.snapshot
        if snapshot.state is not BatchJobState.EXECUTING or snapshot.attempt_id is None:
            raise BatchJobError("batch_job_invalid_state")
        if any(item.result is not None for item in stored.items):
            raise BatchJobError("batch_job_corrupt", 503)
        return BatchMutationRequest(
            operation=snapshot.spec.operation,
            model=snapshot.spec.model,
            schema_id=snapshot.spec.schema_id,
            failure_mode=snapshot.spec.failure_mode,
            items=tuple(item.item for item in stored.items),
        )

    def mark_execution_unknown(
        self,
        *,
        job_id: UUID,
        attempt_id: UUID,
        error_code: str,
    ) -> StoredBatchMutationJob:
        try:
            stored = self._store.mark_execution_unknown(
                job_id=job_id,
                attempt_id=attempt_id,
                occurred_at=self._now(),
                error_code=error_code,
            )
        except Exception:
            raise BatchJobError("batch_job_store_unavailable", 503) from None
        _verify_job(stored)
        if stored.snapshot.state is not BatchJobState.EXECUTION_UNKNOWN:
            raise BatchJobError("batch_job_corrupt", 503)
        return stored

    def finish_execution(
        self,
        *,
        job_id: UUID,
        attempt_id: UUID,
        result: BatchMutationResult,
        error_code: str | None = None,
    ) -> BatchCommandReceipt:
        try:
            stored = self._store.finish_execution(
                job_id=job_id,
                attempt_id=attempt_id,
                result=result,
                completed_at=self._now(),
                error_code=error_code,
            )
        except Exception as error:
            code = str(getattr(error, "code", "batch_job_store_unavailable"))
            raise BatchJobError(code, 503) from None
        _verify_job(stored)
        return batch_command_receipt(stored)

    def terminal_receipt(
        self,
        job_id: UUID,
        *,
        actor: ChatActor,
        expected_fingerprint: str,
    ) -> BatchCommandReceipt | None:
        stored = self.get_bound(
            job_id,
            actor=actor,
            expected_fingerprint=expected_fingerprint,
        )
        if stored.snapshot.state in {
            BatchJobState.COMPLETED,
            BatchJobState.PARTIAL,
            BatchJobState.FAILED,
        }:
            return batch_command_receipt(stored)
        return None

    def _new_id(self) -> UUID:
        value = self._id_factory()
        if not isinstance(value, UUID):
            raise BatchJobError("batch_job_id_unavailable", 503)
        return value

    def _now(self) -> datetime:
        value = self._clock()
        if not isinstance(value, datetime) or value.tzinfo is None:
            raise BatchJobError("clock_unavailable", 503)
        return value.astimezone(UTC)


def batch_item_fingerprint(item: object) -> Fingerprint:
    if not hasattr(item, "model_dump"):
        raise BatchJobError("batch_item_invalid", 422)
    payload = cast(object, item).model_dump(mode="json")  # type: ignore[attr-defined]
    return cast(Fingerprint, _fingerprint("batch-item", payload))


def batch_job_fingerprint(
    job_id: UUID,
    spec: BatchMutationJobSpec,
    items: tuple[BatchMutationJobItem, ...],
) -> Fingerprint:
    payload = {
        "job_id": str(job_id),
        "spec": spec.model_dump(mode="json"),
        "item_fingerprints": [item.item_fingerprint for item in items],
    }
    return cast(Fingerprint, _fingerprint("batch-job", payload))


def batch_command_receipt(stored: StoredBatchMutationJob) -> BatchCommandReceipt:
    _verify_job(stored)
    snapshot = stored.snapshot
    if snapshot.state not in {
        BatchJobState.COMPLETED,
        BatchJobState.PARTIAL,
        BatchJobState.FAILED,
    }:
        raise BatchJobError("batch_job_not_terminal")
    if snapshot.attempt_id is None or snapshot.completed_at is None:
        raise BatchJobError("batch_job_corrupt", 503)
    failed = tuple(
        item.item.source_ref
        for item in stored.items
        if item.result is not None and item.result.error_code is not None
    )
    return BatchCommandReceipt(
        job_id=snapshot.job_id,
        attempt_id=snapshot.attempt_id,
        job_fingerprint=snapshot.job_fingerprint,
        state=snapshot.state,
        total_items=snapshot.item_count,
        applied_items=snapshot.applied_count,
        failed_items=snapshot.failed_count,
        failed_source_refs=failed[:MAX_BATCH_FAILURE_PREVIEW],
        completed_at=snapshot.completed_at,
        error_code=snapshot.error_code,
    )


def _require_request_matches_spec(
    request: BatchMutationRequest,
    spec: BatchMutationJobSpec,
) -> None:
    if (
        request.operation is not spec.operation
        or request.model != spec.model
        or request.schema_id != spec.schema_id
        or request.failure_mode is not spec.failure_mode
    ):
        raise BatchJobError("batch_job_spec_mismatch", 422)


def _verify_job(stored: StoredBatchMutationJob) -> None:
    snapshot = stored.snapshot
    if len(stored.items) != snapshot.item_count or not stored.items:
        raise BatchJobError("batch_job_corrupt", 503)
    positions = tuple(item.position for item in stored.items)
    if positions != tuple(range(len(stored.items))):
        raise BatchJobError("batch_job_corrupt", 503)
    refs = tuple(item.item.source_ref for item in stored.items)
    if len(refs) != len(set(refs)):
        raise BatchJobError("batch_job_corrupt", 503)
    for item in stored.items:
        if item.item.operation is not snapshot.spec.operation:
            raise BatchJobError("batch_job_corrupt", 503)
        expected_item = batch_item_fingerprint(item.item)
        if not _constant_time_equal(expected_item, item.item_fingerprint):
            raise BatchJobError("batch_job_corrupt", 503)
    expected_job = batch_job_fingerprint(snapshot.job_id, snapshot.spec, stored.items)
    if not _constant_time_equal(expected_job, snapshot.job_fingerprint):
        raise BatchJobError("batch_job_corrupt", 503)
    applied = sum(
        item.result is not None and item.result.error_code is None for item in stored.items
    )
    failed = sum(
        item.result is not None and item.result.error_code is not None for item in stored.items
    )
    if snapshot.state in {BatchJobState.PREPARED, BatchJobState.EXECUTING}:
        if applied or failed:
            raise BatchJobError("batch_job_corrupt", 503)
    elif snapshot.state is BatchJobState.EXECUTION_UNKNOWN:
        # The Assistant may not know which effects reached Odoo. Durable Odoo receipts,
        # not local guessing, resolve the next idempotent execution attempt.
        if applied or failed:
            raise BatchJobError("batch_job_corrupt", 503)
    elif applied != snapshot.applied_count or failed != snapshot.failed_count:
        raise BatchJobError("batch_job_corrupt", 503)


def _proposal_handle(snapshot: BatchMutationJobSnapshot) -> BatchProposalHandle:
    source = snapshot.spec.source
    return BatchProposalHandle(
        job_id=snapshot.job_id,
        turn_id=snapshot.spec.turn_id,
        job_fingerprint=snapshot.job_fingerprint,
        operation=snapshot.spec.operation,
        model=snapshot.spec.model,
        item_count=snapshot.item_count,
        failure_mode=snapshot.spec.failure_mode,
        source_provider=source.provider,
        source_display_name=source.display_name,
    )


def _transition_job(
    outcome: BatchJobTransitionOutcome,
    stored: StoredBatchMutationJob | None,
) -> StoredBatchMutationJob:
    if outcome is BatchJobTransitionOutcome.NOT_FOUND:
        raise BatchJobError("batch_job_not_found", 404)
    if outcome is BatchJobTransitionOutcome.BINDING_MISMATCH:
        raise BatchJobError("batch_job_binding_mismatch", 403)
    if outcome is BatchJobTransitionOutcome.FINGERPRINT_MISMATCH:
        raise BatchJobError("batch_job_fingerprint_mismatch")
    if outcome is BatchJobTransitionOutcome.CORRUPT:
        raise BatchJobError("batch_job_corrupt", 503)
    if outcome is BatchJobTransitionOutcome.INVALID_STATE:
        raise BatchJobError("batch_job_invalid_state")
    if outcome not in {
        BatchJobTransitionOutcome.APPLIED,
        BatchJobTransitionOutcome.RESUMED,
    } or stored is None:
        raise BatchJobError("batch_job_store_unavailable", 503)
    return stored


def _fingerprint(domain: str, value: Mapping[str, object] | object) -> str:
    body = json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return f"{domain}:v1:sha256:{hashlib.sha256(body).hexdigest()}"


def _constant_time_equal(left: str, right: str) -> bool:
    return hashlib.sha256(left.encode()).digest() == hashlib.sha256(right.encode()).digest()
