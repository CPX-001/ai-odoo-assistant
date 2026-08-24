"""Ports for executing already-normalized bulk mutations against Odoo."""

from __future__ import annotations

from typing import Protocol

from odoo_ai.contracts.batch import (
    BatchCreateItem,
    BatchDeleteItem,
    BatchFailureMode,
    BatchItemResult,
    BatchPatchItem,
)
from odoo_ai.contracts.batch_job import BatchExecutionContext


class BatchMutationGateway(Protocol):
    """Execute one host-planned chunk and return exactly one result per source row.

    Implementations must be idempotent for one ``BatchExecutionContext``. Repeating a
    chunk after a transport failure must recover the prior result instead of applying
    the mutation a second time.
    """

    async def create_many(
        self,
        *,
        context: BatchExecutionContext,
        model: str,
        schema_id: str,
        items: tuple[BatchCreateItem, ...],
        failure_mode: BatchFailureMode,
    ) -> tuple[BatchItemResult, ...]: ...

    async def patch_many(
        self,
        *,
        context: BatchExecutionContext,
        model: str,
        schema_id: str,
        items: tuple[BatchPatchItem, ...],
        failure_mode: BatchFailureMode,
    ) -> tuple[BatchItemResult, ...]: ...

    async def delete_many(
        self,
        *,
        context: BatchExecutionContext,
        model: str,
        items: tuple[BatchDeleteItem, ...],
        failure_mode: BatchFailureMode,
    ) -> tuple[BatchItemResult, ...]: ...
