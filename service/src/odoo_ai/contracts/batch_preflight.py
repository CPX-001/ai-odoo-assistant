"""Provider-neutral result of validating normalized batch rows without mutation."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from odoo_ai.contracts.batch import (
    MAX_BATCH_ERROR_CODE,
    MAX_BATCH_ITEMS,
    SourceRef,
    BatchMutationKind,
)
from odoo_ai.contracts.action import ModelName


class BatchPreflightIssue(BaseModel):
    """One sanitized row rejection discovered before an executable job is sealed."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    source_ref: SourceRef
    error_code: str = Field(min_length=1, max_length=MAX_BATCH_ERROR_CODE)


class BatchPreflightResult(BaseModel):
    """Exact partition of one preflight request into accepted and rejected rows."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    operation: BatchMutationKind
    model: ModelName
    accepted_source_refs: tuple[SourceRef, ...] = Field(
        default=(), max_length=MAX_BATCH_ITEMS
    )
    issues: tuple[BatchPreflightIssue, ...] = Field(default=(), max_length=MAX_BATCH_ITEMS)

    @model_validator(mode="after")
    def validate_partition(self):
        accepted = self.accepted_source_refs
        rejected = tuple(issue.source_ref for issue in self.issues)
        if (
            not accepted and not rejected
            or len(accepted) != len(set(accepted))
            or len(rejected) != len(set(rejected))
            or set(accepted).intersection(rejected)
            or len(accepted) + len(rejected) > MAX_BATCH_ITEMS
        ):
            raise ValueError("batch preflight partition is invalid")
        return self
