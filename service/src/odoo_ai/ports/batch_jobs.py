"""Persistence boundary for immutable execution-ready batch jobs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from odoo_ai.contracts.batch import BatchMutationResult
from odoo_ai.contracts.batch_job import (
    BatchMutationJobItem,
    BatchMutationJobSnapshot,
)
from odoo_ai.contracts.chat import ChatActor


@dataclass(frozen=True, slots=True)
class StoredBatchMutationJob:
    snapshot: BatchMutationJobSnapshot
    items: tuple[BatchMutationJobItem, ...]


class BatchJobTransitionOutcome(StrEnum):
    APPLIED = "applied"
    RESUMED = "resumed"
    NOT_FOUND = "not_found"
    BINDING_MISMATCH = "binding_mismatch"
    FINGERPRINT_MISMATCH = "fingerprint_mismatch"
    INVALID_STATE = "invalid_state"
    CORRUPT = "corrupt"


@dataclass(frozen=True, slots=True)
class BatchJobTransitionResult:
    outcome: BatchJobTransitionOutcome
    job: StoredBatchMutationJob | None = None


class BatchMutationJobStore(Protocol):
    """Store operations own transaction boundaries and concurrency control."""

    def create(self, job: StoredBatchMutationJob) -> None: ...

    def get(self, job_id: UUID) -> StoredBatchMutationJob | None: ...

    def claim_execution(
        self,
        *,
        job_id: UUID,
        actor: ChatActor,
        expected_fingerprint: str,
        attempt_id: UUID,
        started_at: datetime,
    ) -> BatchJobTransitionResult: ...

    def mark_execution_unknown(
        self,
        *,
        job_id: UUID,
        attempt_id: UUID,
        occurred_at: datetime,
        error_code: str,
    ) -> StoredBatchMutationJob: ...

    def finish_execution(
        self,
        *,
        job_id: UUID,
        attempt_id: UUID,
        result: BatchMutationResult,
        completed_at: datetime,
        error_code: str | None = None,
    ) -> StoredBatchMutationJob: ...
