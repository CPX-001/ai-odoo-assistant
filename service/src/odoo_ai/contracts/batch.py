"""Provider-neutral contracts for bounded bulk Odoo mutations.

These contracts describe already-normalized rows. File parsing, semantic column
mapping and Odoo execution deliberately live in separate layers.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Final, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from odoo_ai.contracts.action import (
    ActionFieldChange,
    Fingerprint,
    ModelName,
    PositiveId,
)

MAX_BATCH_ITEMS: Final = 500
MAX_BATCH_FIELDS: Final = 64
MAX_BATCH_SOURCE_REF: Final = 128
MAX_BATCH_ERROR_CODE: Final = 128


class BatchMutationKind(StrEnum):
    """Closed generic mutation families supported by the batch planner."""

    CREATE = "create"
    PATCH = "patch"
    DELETE = "delete"


class BatchFailureMode(StrEnum):
    """Executor semantics selected by the host, never inferred from row content."""

    ATOMIC_CHUNK = "atomic_chunk"
    CONTINUE_ON_ERROR = "continue_on_error"


class BatchItemState(StrEnum):
    APPLIED = "applied"
    FAILED = "failed"


SourceRef = Annotated[str, Field(min_length=1, max_length=MAX_BATCH_SOURCE_REF)]


class BatchCreateItem(BaseModel):
    """One normalized source row that will create one Odoo record."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    operation: Literal[BatchMutationKind.CREATE] = BatchMutationKind.CREATE
    source_ref: SourceRef
    values: tuple[ActionFieldChange, ...] = Field(
        min_length=1,
        max_length=MAX_BATCH_FIELDS,
    )

    @model_validator(mode="after")
    def validate_fields(self) -> Self:
        _require_unique_fields(self.values)
        return self


class BatchPatchItem(BaseModel):
    """One normalized source row targeting exactly one existing Odoo record."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    operation: Literal[BatchMutationKind.PATCH] = BatchMutationKind.PATCH
    source_ref: SourceRef
    record_id: PositiveId
    changes: tuple[ActionFieldChange, ...] = Field(
        min_length=1,
        max_length=MAX_BATCH_FIELDS,
    )

    @model_validator(mode="after")
    def validate_fields(self) -> Self:
        _require_unique_fields(self.changes)
        return self


class BatchDeleteItem(BaseModel):
    """One normalized source row selecting one record for deletion."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    operation: Literal[BatchMutationKind.DELETE] = BatchMutationKind.DELETE
    source_ref: SourceRef
    record_id: PositiveId


BatchMutationItem = Annotated[
    BatchCreateItem | BatchPatchItem | BatchDeleteItem,
    Field(discriminator="operation"),
]


class BatchMutationRequest(BaseModel):
    """One bounded in-memory batch after semantic resolution and schema validation.

    Large imports are expected to persist normalized rows and feed multiple requests;
    this object is intentionally bounded so neither Codex nor one HTTP payload needs
    to carry an entire workbook. Independent row failures continue by default so a
    single bad spreadsheet row does not roll back unrelated valid rows.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    operation: BatchMutationKind
    model: ModelName
    schema_id: Fingerprint | None = None
    failure_mode: BatchFailureMode = BatchFailureMode.CONTINUE_ON_ERROR
    items: tuple[BatchMutationItem, ...] = Field(min_length=1, max_length=MAX_BATCH_ITEMS)

    @model_validator(mode="after")
    def validate_batch(self) -> Self:
        if any(item.operation is not self.operation for item in self.items):
            raise ValueError("batch items must use the request operation")
        source_refs = tuple(item.source_ref for item in self.items)
        if len(source_refs) != len(set(source_refs)):
            raise ValueError("batch source refs must be unique")
        if self.operation in {BatchMutationKind.CREATE, BatchMutationKind.PATCH}:
            if self.schema_id is None:
                raise ValueError("create and patch batches require an effective schema id")
        elif self.schema_id is not None:
            raise ValueError("delete batches do not carry a write schema id")
        if self.operation is not BatchMutationKind.CREATE:
            record_ids = tuple(item.record_id for item in self.items)  # type: ignore[attr-defined]
            if len(record_ids) != len(set(record_ids)):
                raise ValueError("batch record ids must be unique")
        return self


class BatchItemResult(BaseModel):
    """One row-level result; failures never contain raw exception text."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    source_ref: SourceRef
    state: BatchItemState
    record_id: PositiveId | None = None
    error_code: str | None = Field(default=None, min_length=1, max_length=MAX_BATCH_ERROR_CODE)

    @model_validator(mode="after")
    def validate_outcome(self) -> Self:
        if self.state is BatchItemState.APPLIED:
            if self.error_code is not None or self.record_id is None:
                raise ValueError("applied batch item requires a record id and no error")
        elif self.error_code is None or self.record_id is not None:
            raise ValueError("failed batch item requires an error and no record id")
        return self


class BatchMutationResult(BaseModel):
    """Aggregate result preserving one deterministic outcome per source row."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    operation: BatchMutationKind
    model: ModelName
    total_items: int = Field(strict=True, ge=1, le=MAX_BATCH_ITEMS)
    applied_items: int = Field(strict=True, ge=0, le=MAX_BATCH_ITEMS)
    failed_items: int = Field(strict=True, ge=0, le=MAX_BATCH_ITEMS)
    results: tuple[BatchItemResult, ...] = Field(min_length=1, max_length=MAX_BATCH_ITEMS)

    @model_validator(mode="after")
    def validate_counts(self) -> Self:
        if (
            len(self.results) != self.total_items
            or self.applied_items + self.failed_items != self.total_items
            or sum(item.state is BatchItemState.APPLIED for item in self.results)
            != self.applied_items
        ):
            raise ValueError("batch result counts are inconsistent")
        refs = tuple(item.source_ref for item in self.results)
        if len(refs) != len(set(refs)):
            raise ValueError("batch result source refs must be unique")
        return self


def _require_unique_fields(values: tuple[ActionFieldChange, ...]) -> None:
    fields = tuple(value.field for value in values)
    if len(fields) != len(set(fields)):
        raise ValueError("batch item fields must be unique")
