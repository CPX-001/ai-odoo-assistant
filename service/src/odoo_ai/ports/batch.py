"""Port for executing already-normalized bulk mutations against Odoo."""

from __future__ import annotations

from typing import Protocol

from odoo_ai.contracts.batch import (
    BatchCreateItem,
    BatchDeleteItem,
    BatchFailureMode,
    BatchItemResult,
    BatchPatchItem,
)


class BatchMutationGateway(Protocol):
    """Execute one host-planned chunk and return exactly one result per source row."""

    async def create_many(
        self,
        *,
        model: str,
        schema_id: str,
        items: tuple[BatchCreateItem, ...],
        failure_mode: BatchFailureMode,
    ) -> tuple[BatchItemResult, ...]: ...

    async def patch_many(
        self,
        *,
        model: str,
        schema_id: str,
        items: tuple[BatchPatchItem, ...],
        failure_mode: BatchFailureMode,
    ) -> tuple[BatchItemResult, ...]: ...

    async def delete_many(
        self,
        *,
        model: str,
        items: tuple[BatchDeleteItem, ...],
        failure_mode: BatchFailureMode,
    ) -> tuple[BatchItemResult, ...]: ...
