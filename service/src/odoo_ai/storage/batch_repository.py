"""PostgreSQL adapter for immutable execution-ready batch mutation jobs."""

from __future__ import annotations

import hmac
from datetime import datetime
from typing import cast
from uuid import UUID

from pydantic import JsonValue, TypeAdapter, ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from odoo_ai.application.batch_jobs import (
    batch_item_fingerprint,
    batch_job_fingerprint,
)
from odoo_ai.contracts.batch import (
    BatchItemResult,
    BatchItemState,
    BatchMutationItem,
    BatchMutationResult,
)
from odoo_ai.contracts.batch_job import (
    BatchJobState,
    BatchMutationJobItem,
    BatchMutationJobSnapshot,
    BatchMutationJobSpec,
)
from odoo_ai.contracts.chat import ChatActor
from odoo_ai.ports.batch_jobs import (
    BatchJobTransitionOutcome,
    BatchJobTransitionResult,
    StoredBatchMutationJob,
)
from odoo_ai.storage.batch_models import (
    BatchMutationAuditRecord,
    BatchMutationItemRecord,
    BatchMutationJobRecord,
)
from odoo_ai.storage.database import SessionFactory, session_scope

_ITEM_ADAPTER: TypeAdapter[BatchMutationItem] = TypeAdapter(BatchMutationItem)


class BatchJobStoreError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class SqlBatchMutationJobStore:
    """Serialize job claims/results and fail closed on persisted-data drift."""

    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    def create(self, job: StoredBatchMutationJob) -> None:
        snapshot = job.snapshot
        spec = snapshot.spec
        if snapshot.state is not BatchJobState.PREPARED:
            raise BatchJobStoreError("batch_job_invalid_state")
        record = BatchMutationJobRecord(
            job_id=snapshot.job_id,
            turn_id=spec.turn_id,
            conversation_id=spec.conversation_id,
            instance_id=spec.instance_id,
            database=spec.actor.database,
            uid=spec.actor.uid,
            company_id=spec.company_id,
            allowed_company_ids=list(spec.allowed_company_ids),
            operation=spec.operation.value,
            target_model=spec.model,
            schema_id=spec.schema_id,
            failure_mode=spec.failure_mode.value,
            policy_revision=spec.policy_revision,
            source_provider=spec.source.provider,
            source_reference=spec.source.reference,
            source_fingerprint=spec.source.content_fingerprint,
            spec_payload=cast(dict[str, JsonValue], spec.model_dump(mode="json")),
            job_fingerprint=snapshot.job_fingerprint,
            state=snapshot.state.value,
            item_count=snapshot.item_count,
            applied_count=0,
            failed_count=0,
            state_version=0,
            created_at=snapshot.created_at,
            updated_at=snapshot.created_at,
        )
        rows = [
            BatchMutationItemRecord(
                job_id=snapshot.job_id,
                position=item.position,
                source_ref=item.item.source_ref,
                item_payload=cast(dict[str, JsonValue], item.item.model_dump(mode="json")),
                item_fingerprint=item.item_fingerprint,
                state="pending",
                result_payload=None,
                created_at=snapshot.created_at,
                updated_at=snapshot.created_at,
            )
            for item in job.items
        ]
        try:
            with session_scope(self._session_factory) as session:
                session.add(record)
                session.add_all(rows)
                session.flush()
                _audit(session, record, "prepared", snapshot.created_at)
        except IntegrityError:
            raise BatchJobStoreError("batch_job_conflict") from None

    def get(self, job_id: UUID) -> StoredBatchMutationJob | None:
        with self._session_factory() as session:
            record = session.get(BatchMutationJobRecord, job_id)
            return None if record is None else _snapshot(session, record)

    def claim_execution(
        self,
        *,
        job_id: UUID,
        actor: ChatActor,
        expected_fingerprint: str,
        attempt_id: UUID,
        started_at: datetime,
    ) -> BatchJobTransitionResult:
        with session_scope(self._session_factory) as session:
            record = session.scalar(
                select(BatchMutationJobRecord)
                .where(BatchMutationJobRecord.job_id == job_id)
                .with_for_update()
            )
            if record is None:
                return BatchJobTransitionResult(BatchJobTransitionOutcome.NOT_FOUND)
            try:
                current = _snapshot(session, record)
            except BatchJobStoreError:
                return BatchJobTransitionResult(BatchJobTransitionOutcome.CORRUPT)
            if current.snapshot.spec.actor != actor:
                return BatchJobTransitionResult(
                    BatchJobTransitionOutcome.BINDING_MISMATCH,
                    current,
                )
            if not hmac.compare_digest(
                current.snapshot.job_fingerprint,
                expected_fingerprint,
            ):
                return BatchJobTransitionResult(
                    BatchJobTransitionOutcome.FINGERPRINT_MISMATCH,
                    current,
                )
            if current.snapshot.state is BatchJobState.PREPARED:
                record.state = BatchJobState.EXECUTING.value
                record.attempt_id = attempt_id
                record.execution_started_at = started_at
                record.error_code = None
                record.state_version += 1
                record.updated_at = started_at
                session.flush()
                _audit(session, record, "execution_claimed", started_at)
                return BatchJobTransitionResult(
                    BatchJobTransitionOutcome.APPLIED,
                    _snapshot(session, record),
                )
            if current.snapshot.state is BatchJobState.EXECUTION_UNKNOWN:
                if record.attempt_id is None:
                    return BatchJobTransitionResult(BatchJobTransitionOutcome.CORRUPT)
                record.state = BatchJobState.EXECUTING.value
                record.error_code = None
                record.state_version += 1
                record.updated_at = started_at
                session.flush()
                _audit(session, record, "execution_resumed", started_at)
                return BatchJobTransitionResult(
                    BatchJobTransitionOutcome.RESUMED,
                    _snapshot(session, record),
                )
            return BatchJobTransitionResult(
                BatchJobTransitionOutcome.INVALID_STATE,
                current,
            )

    def mark_execution_unknown(
        self,
        *,
        job_id: UUID,
        attempt_id: UUID,
        occurred_at: datetime,
        error_code: str,
    ) -> StoredBatchMutationJob:
        with session_scope(self._session_factory) as session:
            record = session.scalar(
                select(BatchMutationJobRecord)
                .where(BatchMutationJobRecord.job_id == job_id)
                .with_for_update()
            )
            if (
                record is None
                or record.state != BatchJobState.EXECUTING.value
                or record.attempt_id != attempt_id
            ):
                raise BatchJobStoreError("batch_job_invalid_state")
            record.state = BatchJobState.EXECUTION_UNKNOWN.value
            record.error_code = error_code
            record.state_version += 1
            record.updated_at = occurred_at
            session.flush()
            _audit(session, record, "execution_unknown", occurred_at)
            return _snapshot(session, record)

    def finish_execution(
        self,
        *,
        job_id: UUID,
        attempt_id: UUID,
        result: BatchMutationResult,
        completed_at: datetime,
        error_code: str | None = None,
    ) -> StoredBatchMutationJob:
        with session_scope(self._session_factory) as session:
            record = session.scalar(
                select(BatchMutationJobRecord)
                .where(BatchMutationJobRecord.job_id == job_id)
                .with_for_update()
            )
            if (
                record is None
                or record.state != BatchJobState.EXECUTING.value
                or record.attempt_id != attempt_id
            ):
                raise BatchJobStoreError("batch_job_invalid_state")
            current = _snapshot(session, record)
            if (
                result.operation is not current.snapshot.spec.operation
                or result.model != current.snapshot.spec.model
                or result.total_items != current.snapshot.item_count
            ):
                raise BatchJobStoreError("batch_job_result_mismatch")
            expected_refs = tuple(item.item.source_ref for item in current.items)
            actual_refs = tuple(item.source_ref for item in result.results)
            if actual_refs != expected_refs:
                raise BatchJobStoreError("batch_job_result_mismatch")

            rows = tuple(
                session.scalars(
                    select(BatchMutationItemRecord)
                    .where(BatchMutationItemRecord.job_id == job_id)
                    .order_by(BatchMutationItemRecord.position)
                    .with_for_update()
                )
            )
            if len(rows) != len(result.results):
                raise BatchJobStoreError("batch_job_corrupt")
            for row, item_result in zip(rows, result.results, strict=True):
                if row.source_ref != item_result.source_ref or row.state != "pending":
                    raise BatchJobStoreError("batch_job_corrupt")
                row.state = (
                    "applied"
                    if item_result.state is BatchItemState.APPLIED
                    else "failed"
                )
                row.result_payload = cast(
                    dict[str, JsonValue],
                    item_result.model_dump(mode="json"),
                )
                row.updated_at = completed_at

            state = _terminal_state(result)
            record.state = state.value
            record.applied_count = result.applied_items
            record.failed_count = result.failed_items
            record.completed_at = completed_at
            record.error_code = error_code
            record.state_version += 1
            record.updated_at = completed_at
            session.flush()
            _audit(session, record, state.value, completed_at)
            return _snapshot(session, record)


def _snapshot(
    session: Session,
    record: BatchMutationJobRecord,
) -> StoredBatchMutationJob:
    rows = tuple(
        session.scalars(
            select(BatchMutationItemRecord)
            .where(BatchMutationItemRecord.job_id == record.job_id)
            .order_by(BatchMutationItemRecord.position)
        )
    )
    try:
        spec = BatchMutationJobSpec.model_validate(record.spec_payload)
        state = BatchJobState(record.state)
        items: list[BatchMutationJobItem] = []
        for row in rows:
            item = _ITEM_ADAPTER.validate_python(row.item_payload)
            result = (
                None
                if row.result_payload is None
                else BatchItemResult.model_validate(row.result_payload)
            )
            expected_state = (
                "pending"
                if result is None
                else "applied"
                if result.state is BatchItemState.APPLIED
                else "failed"
            )
            if row.source_ref != item.source_ref or row.state != expected_state:
                raise ValueError("batch item materialization mismatch")
            items.append(
                BatchMutationJobItem(
                    position=row.position,
                    item=item,
                    item_fingerprint=cast(str, row.item_fingerprint),
                    result=result,
                )
            )
        snapshot = BatchMutationJobSnapshot(
            job_id=record.job_id,
            spec=spec,
            job_fingerprint=cast(str, record.job_fingerprint),
            state=state,
            item_count=record.item_count,
            applied_count=record.applied_count,
            failed_count=record.failed_count,
            attempt_id=record.attempt_id,
            created_at=record.created_at,
            execution_started_at=record.execution_started_at,
            completed_at=record.completed_at,
            error_code=record.error_code,
        )
    except (ValidationError, ValueError, TypeError):
        raise BatchJobStoreError("batch_job_corrupt") from None

    if (
        spec.turn_id != record.turn_id
        or spec.conversation_id != record.conversation_id
        or spec.instance_id != record.instance_id
        or spec.actor.database != record.database
        or spec.actor.uid != record.uid
        or spec.company_id != record.company_id
        or spec.allowed_company_ids != tuple(record.allowed_company_ids)
        or spec.operation.value != record.operation
        or spec.model != record.target_model
        or spec.schema_id != record.schema_id
        or spec.failure_mode.value != record.failure_mode
        or spec.policy_revision != record.policy_revision
        or spec.source.provider != record.source_provider
        or spec.source.reference != record.source_reference
        or spec.source.content_fingerprint != record.source_fingerprint
        or record.state_version < 0
        or len(rows) != record.item_count
    ):
        raise BatchJobStoreError("batch_job_corrupt")

    stored_items = tuple(items)
    if tuple(item.position for item in stored_items) != tuple(range(len(stored_items))):
        raise BatchJobStoreError("batch_job_corrupt")
    for item in stored_items:
        if not hmac.compare_digest(
            item.item_fingerprint,
            batch_item_fingerprint(item.item),
        ):
            raise BatchJobStoreError("batch_job_corrupt")
    expected_job = batch_job_fingerprint(snapshot.job_id, spec, stored_items)
    if not hmac.compare_digest(snapshot.job_fingerprint, expected_job):
        raise BatchJobStoreError("batch_job_corrupt")
    return StoredBatchMutationJob(snapshot=snapshot, items=stored_items)


def _terminal_state(result: BatchMutationResult) -> BatchJobState:
    if result.failed_items == 0:
        return BatchJobState.COMPLETED
    if result.applied_items == 0:
        return BatchJobState.FAILED
    return BatchJobState.PARTIAL


def _audit(
    session: Session,
    record: BatchMutationJobRecord,
    event_type: str,
    occurred_at: datetime,
) -> None:
    session.add(
        BatchMutationAuditRecord(
            job_id=record.job_id,
            attempt_id=record.attempt_id,
            event_type=event_type,
            state=record.state,
            actor_uid=record.uid,
            job_fingerprint=record.job_fingerprint,
            error_code=record.error_code,
            attributes={
                "applied_count": record.applied_count,
                "failed_count": record.failed_count,
                "failure_mode": record.failure_mode,
                "item_count": record.item_count,
                "operation": record.operation,
                "source_provider": record.source_provider,
                "state_version": record.state_version,
                "target_model": record.target_model,
            },
            created_at=occurred_at,
        )
    )
