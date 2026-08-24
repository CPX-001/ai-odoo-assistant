"""Durable execution-ready batch proposal contracts.

A BatchMutationJob is intentionally downstream of parsing and semantic mapping. It
contains only normalized typed Odoo mutations plus provenance. Raw files and extracted
text belong to ingestion/content providers, not to this contract.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

from odoo_ai.contracts.action import Fingerprint, Revision
from odoo_ai.contracts.batch import (
    MAX_BATCH_ITEMS,
    BatchFailureMode,
    BatchItemResult,
    BatchMutationItem,
    BatchMutationKind,
)
from odoo_ai.contracts.chat import ChatActor
from odoo_ai.contracts.content_source import ContentSourceDescriptor

MAX_BATCH_FAILURE_PREVIEW: int = 50


class BatchJobState(StrEnum):
    PREPARED = "prepared"
    EXECUTING = "executing"
    EXECUTION_UNKNOWN = "execution_unknown"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"


class BatchMutationJobSpec(BaseModel):
    """Immutable actor/model/source binding for one bounded execution batch."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    turn_id: UUID | None = None
    conversation_id: UUID | None = None
    actor: ChatActor
    instance_id: str = Field(min_length=1, max_length=255)
    company_id: int = Field(strict=True, gt=0)
    allowed_company_ids: tuple[int, ...] = Field(min_length=1, max_length=16)
    operation: BatchMutationKind
    model: Annotated[str, Field(pattern=r"^[A-Za-z_][A-Za-z0-9_.]{0,127}$")]
    schema_id: Fingerprint | None = None
    failure_mode: BatchFailureMode = BatchFailureMode.CONTINUE_ON_ERROR
    policy_revision: Revision
    source: ContentSourceDescriptor

    @model_validator(mode="after")
    def validate_binding(self) -> Self:
        if (
            self.company_id not in self.allowed_company_ids
            or self.allowed_company_ids != tuple(sorted(set(self.allowed_company_ids)))
        ):
            raise ValueError("batch job company binding is invalid")
        if self.operation in {BatchMutationKind.CREATE, BatchMutationKind.PATCH}:
            if self.schema_id is None:
                raise ValueError("batch create/patch job requires schema")
        elif self.schema_id is not None:
            raise ValueError("batch delete job cannot carry write schema")
        return self


class BatchMutationJobItem(BaseModel):
    """One immutable ordered row stored outside the agent plan payload."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    position: int = Field(strict=True, ge=0, lt=MAX_BATCH_ITEMS)
    item: BatchMutationItem
    item_fingerprint: Fingerprint
    result: BatchItemResult | None = None

    @model_validator(mode="after")
    def validate_result_binding(self) -> Self:
        if self.result is not None and self.result.source_ref != self.item.source_ref:
            raise ValueError("batch item result source binding is invalid")
        return self


class BatchMutationJobSnapshot(BaseModel):
    """Sanitized durable job state; row payloads are queried separately."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    job_id: UUID
    spec: BatchMutationJobSpec
    job_fingerprint: Fingerprint
    state: BatchJobState
    item_count: int = Field(strict=True, ge=1, le=MAX_BATCH_ITEMS)
    applied_count: int = Field(strict=True, ge=0, le=MAX_BATCH_ITEMS)
    failed_count: int = Field(strict=True, ge=0, le=MAX_BATCH_ITEMS)
    attempt_id: UUID | None = None
    created_at: datetime
    execution_started_at: datetime | None = None
    completed_at: datetime | None = None
    error_code: str | None = Field(default=None, min_length=1, max_length=128)

    @model_validator(mode="after")
    def validate_state_shape(self) -> Self:
        terminal = self.state in {
            BatchJobState.COMPLETED,
            BatchJobState.PARTIAL,
            BatchJobState.FAILED,
        }
        active_or_unknown = self.state in {
            BatchJobState.EXECUTING,
            BatchJobState.EXECUTION_UNKNOWN,
        }
        if self.state is BatchJobState.PREPARED:
            if (
                self.attempt_id is not None
                or self.execution_started_at is not None
                or self.completed_at is not None
            ):
                raise ValueError("prepared batch job has execution state")
        elif active_or_unknown:
            if (
                self.attempt_id is None
                or self.execution_started_at is None
                or self.completed_at is not None
            ):
                raise ValueError("active batch job state is invalid")
        elif terminal and (
            self.attempt_id is None
            or self.execution_started_at is None
            or self.completed_at is None
        ):
            raise ValueError("terminal batch job requires execution state")
        if self.applied_count + self.failed_count > self.item_count:
            raise ValueError("batch job result counts exceed item count")
        if terminal and self.applied_count + self.failed_count != self.item_count:
            raise ValueError("terminal batch job result counts are incomplete")
        if self.state is BatchJobState.COMPLETED and self.failed_count:
            raise ValueError("completed batch job cannot contain failures")
        if self.state is BatchJobState.PARTIAL and not (
            self.applied_count and self.failed_count
        ):
            raise ValueError("partial batch job requires successes and failures")
        if self.state is BatchJobState.FAILED and self.applied_count:
            raise ValueError("failed batch job cannot contain applied rows")
        return self


class BatchProposalHandle(BaseModel):
    """Small browser/plan-safe handle for an immutable batch proposal."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    job_id: UUID
    turn_id: UUID | None = None
    job_fingerprint: Fingerprint
    operation: BatchMutationKind
    model: str = Field(pattern=r"^[A-Za-z_][A-Za-z0-9_.]{0,127}$")
    item_count: int = Field(strict=True, ge=1, le=MAX_BATCH_ITEMS)
    failure_mode: BatchFailureMode
    source_provider: str = Field(pattern=r"^[a-z][a-z0-9_.-]{0,63}$")
    source_display_name: str | None = Field(default=None, min_length=1, max_length=255)


class BatchProposalTrace(BaseModel):
    """Host-only binding between one successful preview tool call and its sealed job."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    tool_name: str = Field(min_length=1, max_length=128)
    arguments: dict[str, JsonValue] = Field(max_length=32)
    job_id: UUID
    job_fingerprint: Fingerprint


class BatchExecutionContext(BaseModel):
    """Opaque host authority binding passed to an idempotent batch gateway.

    The gateway must treat ``job_id + attempt_id`` as the execution identity and must
    never create a second effect for a row/chunk already completed under that identity.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    job_id: UUID
    attempt_id: UUID
    authorization_id: UUID
    job_fingerprint: Fingerprint
    instance_id: str = Field(min_length=1, max_length=255)
    database: str = Field(min_length=1, max_length=128)
    uid: int = Field(strict=True, gt=0)
    company_id: int = Field(strict=True, gt=0)
    allowed_company_ids: tuple[int, ...] = Field(min_length=1, max_length=16)
    policy_revision: Revision

    @model_validator(mode="after")
    def validate_actor(self) -> Self:
        if (
            self.database != self.database.strip()
            or any(ord(character) < 32 for character in self.database)
            or self.company_id not in self.allowed_company_ids
            or self.allowed_company_ids != tuple(sorted(set(self.allowed_company_ids)))
        ):
            raise ValueError("batch execution actor binding is invalid")
        return self


class BatchCommandReceipt(BaseModel):
    """Compact plan receipt; complete per-row detail remains in the batch store."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    job_id: UUID
    attempt_id: UUID
    job_fingerprint: Fingerprint
    state: BatchJobState
    total_items: int = Field(strict=True, ge=1, le=MAX_BATCH_ITEMS)
    applied_items: int = Field(strict=True, ge=0, le=MAX_BATCH_ITEMS)
    failed_items: int = Field(strict=True, ge=0, le=MAX_BATCH_ITEMS)
    failed_source_refs: tuple[str, ...] = Field(default=(), max_length=MAX_BATCH_FAILURE_PREVIEW)
    completed_at: datetime
    error_code: str | None = Field(default=None, min_length=1, max_length=128)

    @model_validator(mode="after")
    def validate_counts(self) -> Self:
        if self.applied_items + self.failed_items != self.total_items:
            raise ValueError("batch receipt counts are inconsistent")
        if self.state not in {
            BatchJobState.COMPLETED,
            BatchJobState.PARTIAL,
            BatchJobState.FAILED,
        }:
            raise ValueError("batch receipt must be terminal")
        if self.state is BatchJobState.COMPLETED and self.failed_items:
            raise ValueError("completed batch receipt cannot contain failures")
        if self.state is BatchJobState.PARTIAL and not (
            self.applied_items and self.failed_items
        ):
            raise ValueError("partial batch receipt requires mixed results")
        if self.state is BatchJobState.FAILED and self.applied_items:
            raise ValueError("failed batch receipt cannot contain applied rows")
        if len(self.failed_source_refs) > self.failed_items:
            raise ValueError("batch receipt failure preview is inconsistent")
        return self
