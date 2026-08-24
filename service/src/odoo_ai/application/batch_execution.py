"""Execute normalized bulk mutations through a bounded gateway.

This layer owns chunk sequencing, result integrity and aggregation. It does not
know about HTTP, Odoo ORM, files, Codex or approval storage.
"""

from __future__ import annotations

from collections.abc import Sequence

from odoo_ai.application.batching import (
    BatchPlannerLimits,
    BatchPlanningError,
    chunk_items,
    plan_batch_mutation,
)
from odoo_ai.contracts.batch import (
    BatchCreateItem,
    BatchDeleteItem,
    BatchItemResult,
    BatchItemState,
    BatchMutationKind,
    BatchMutationRequest,
    BatchMutationResult,
    BatchPatchItem,
)
from odoo_ai.contracts.batch_job import BatchExecutionContext
from odoo_ai.ports.batch import BatchMutationGateway


class BatchExecutionError(RuntimeError):
    def __init__(self, code: str, status_code: int = 409) -> None:
        super().__init__(code)
        self.code = code
        self.status_code = status_code


class BatchMutationExecutionService:
    """Run chunks sequentially and preserve one outcome for every source row."""

    def __init__(
        self,
        gateway: BatchMutationGateway,
        *,
        limits: BatchPlannerLimits | None = None,
    ) -> None:
        self._gateway = gateway
        self._limits = limits

    async def execute(
        self,
        request: BatchMutationRequest,
        *,
        context: BatchExecutionContext,
    ) -> BatchMutationResult:
        try:
            plan = plan_batch_mutation(request, limits=self._limits)
        except BatchPlanningError as error:
            raise BatchExecutionError(str(error), 422) from None

        by_ref: dict[str, BatchItemResult] = {}
        for chunk in plan.chunks:
            raw_items = chunk_items(request, chunk)
            try:
                chunk_results = await self._execute_chunk(
                    request,
                    raw_items,
                    context=context,
                )
            except BatchExecutionError:
                raise
            except Exception:
                raise BatchExecutionError("batch_gateway_unavailable", 503) from None
            self._validate_chunk_results(raw_items, chunk_results)
            for result in chunk_results:
                if result.source_ref in by_ref:
                    raise BatchExecutionError("batch_gateway_result_corrupt", 502)
                by_ref[result.source_ref] = result

        if len(by_ref) != len(request.items):
            raise BatchExecutionError("batch_gateway_result_incomplete", 502)
        ordered = tuple(by_ref[item.source_ref] for item in request.items)
        applied = sum(item.state is BatchItemState.APPLIED for item in ordered)
        return BatchMutationResult(
            operation=request.operation,
            model=request.model,
            total_items=len(ordered),
            applied_items=applied,
            failed_items=len(ordered) - applied,
            results=ordered,
        )

    async def _execute_chunk(
        self,
        request: BatchMutationRequest,
        raw_items: Sequence[BatchCreateItem | BatchPatchItem | BatchDeleteItem],
        *,
        context: BatchExecutionContext,
    ) -> tuple[BatchItemResult, ...]:
        if request.operation is BatchMutationKind.CREATE:
            if request.schema_id is None or not all(
                isinstance(item, BatchCreateItem) for item in raw_items
            ):
                raise BatchExecutionError("invalid_batch_chunk", 422)
            return await self._gateway.create_many(
                context=context,
                model=request.model,
                schema_id=request.schema_id,
                items=tuple(item for item in raw_items if isinstance(item, BatchCreateItem)),
                failure_mode=request.failure_mode,
            )
        if request.operation is BatchMutationKind.PATCH:
            if request.schema_id is None or not all(
                isinstance(item, BatchPatchItem) for item in raw_items
            ):
                raise BatchExecutionError("invalid_batch_chunk", 422)
            return await self._gateway.patch_many(
                context=context,
                model=request.model,
                schema_id=request.schema_id,
                items=tuple(item for item in raw_items if isinstance(item, BatchPatchItem)),
                failure_mode=request.failure_mode,
            )
        if not all(isinstance(item, BatchDeleteItem) for item in raw_items):
            raise BatchExecutionError("invalid_batch_chunk", 422)
        return await self._gateway.delete_many(
            context=context,
            model=request.model,
            items=tuple(item for item in raw_items if isinstance(item, BatchDeleteItem)),
            failure_mode=request.failure_mode,
        )

    @staticmethod
    def _validate_chunk_results(
        items: Sequence[BatchCreateItem | BatchPatchItem | BatchDeleteItem],
        results: Sequence[BatchItemResult],
    ) -> None:
        expected = tuple(item.source_ref for item in items)
        actual = tuple(result.source_ref for result in results)
        if (
            len(actual) != len(expected)
            or len(actual) != len(set(actual))
            or set(actual) != set(expected)
        ):
            raise BatchExecutionError("batch_gateway_result_corrupt", 502)
