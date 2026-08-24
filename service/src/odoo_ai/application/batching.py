"""Deterministic chunk planning for normalized bulk mutations.

The planner owns batching strategy only. It does not parse files, infer fields,
access Odoo, approve writes or execute ORM calls.
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from typing import Final

from odoo_ai.contracts.batch import (
    BatchCreateItem,
    BatchDeleteItem,
    BatchMutationKind,
    BatchMutationRequest,
    BatchPatchItem,
)

DEFAULT_CREATE_CHUNK_SIZE: Final = 50
DEFAULT_PATCH_CHUNK_SIZE: Final = 50
DEFAULT_DELETE_CHUNK_SIZE: Final = 100
MAX_CHUNK_SIZE: Final = 200


class BatchPlanningError(ValueError):
    """Raised when host-owned batching limits are invalid."""


@dataclass(frozen=True, slots=True)
class BatchPlannerLimits:
    """Conservative defaults suitable for modest self-hosted Odoo servers."""

    create_chunk_size: int = DEFAULT_CREATE_CHUNK_SIZE
    patch_chunk_size: int = DEFAULT_PATCH_CHUNK_SIZE
    delete_chunk_size: int = DEFAULT_DELETE_CHUNK_SIZE

    def __post_init__(self) -> None:
        for value in (
            self.create_chunk_size,
            self.patch_chunk_size,
            self.delete_chunk_size,
        ):
            if type(value) is not int or not 1 <= value <= MAX_CHUNK_SIZE:
                raise BatchPlanningError("invalid_batch_chunk_size")


@dataclass(frozen=True, slots=True)
class BatchChunk:
    """One future ORM call group over indexes in the normalized request."""

    index: int
    operation: BatchMutationKind
    item_indexes: tuple[int, ...]
    uniform_values: bool


@dataclass(frozen=True, slots=True)
class BatchExecutionPlan:
    """Stable plan used by adapters/jobs without embedding the row payload twice."""

    operation: BatchMutationKind
    total_items: int
    estimated_orm_calls: int
    chunks: tuple[BatchChunk, ...]


def plan_batch_mutation(
    request: BatchMutationRequest,
    *,
    limits: BatchPlannerLimits | None = None,
) -> BatchExecutionPlan:
    """Plan efficient ORM-sized chunks without reordering source-row identity.

    Creates and deletes preserve contiguous source order. Patches are grouped by
    identical field/value assignments so a future Odoo adapter can use one
    ``recordset.write(values)`` when several records receive exactly the same values.
    Heterogeneous updates remain bounded chunks instead of pretending Odoo exposes a
    native heterogeneous multi-update operation.
    """

    limits = limits or BatchPlannerLimits()
    if request.operation is BatchMutationKind.CREATE:
        chunks = _simple_chunks(
            request.operation,
            len(request.items),
            limits.create_chunk_size,
            uniform_values=False,
        )
    elif request.operation is BatchMutationKind.DELETE:
        chunks = _simple_chunks(
            request.operation,
            len(request.items),
            limits.delete_chunk_size,
            uniform_values=False,
        )
    else:
        chunks = _patch_chunks(request, limits.patch_chunk_size)
    return BatchExecutionPlan(
        operation=request.operation,
        total_items=len(request.items),
        estimated_orm_calls=len(chunks),
        chunks=chunks,
    )


def _simple_chunks(
    operation: BatchMutationKind,
    total: int,
    size: int,
    *,
    uniform_values: bool,
) -> tuple[BatchChunk, ...]:
    chunks: list[BatchChunk] = []
    for start in range(0, total, size):
        chunks.append(
            BatchChunk(
                index=len(chunks),
                operation=operation,
                item_indexes=tuple(range(start, min(start + size, total))),
                uniform_values=uniform_values,
            )
        )
    return tuple(chunks)


def _patch_chunks(
    request: BatchMutationRequest,
    size: int,
) -> tuple[BatchChunk, ...]:
    groups: OrderedDict[tuple[tuple[str, str, object], ...], list[int]] = OrderedDict()
    for index, raw_item in enumerate(request.items):
        if not isinstance(raw_item, BatchPatchItem):
            raise BatchPlanningError("invalid_patch_batch")
        signature = _patch_signature(raw_item)
        groups.setdefault(signature, []).append(index)

    chunks: list[BatchChunk] = []
    for indexes in groups.values():
        for start in range(0, len(indexes), size):
            chunks.append(
                BatchChunk(
                    index=len(chunks),
                    operation=BatchMutationKind.PATCH,
                    item_indexes=tuple(indexes[start : start + size]),
                    uniform_values=True,
                )
            )
    return tuple(chunks)


def _patch_signature(item: BatchPatchItem) -> tuple[tuple[str, str, object], ...]:
    return tuple(
        sorted(
            (
                change.field,
                change.value.kind.value,
                change.value.value,
            )
            for change in item.changes
        )
    )


def chunk_items(
    request: BatchMutationRequest,
    chunk: BatchChunk,
) -> tuple[BatchCreateItem | BatchPatchItem | BatchDeleteItem, ...]:
    """Resolve a planned chunk back to its normalized rows with bounds checking."""

    if chunk.operation is not request.operation:
        raise BatchPlanningError("batch_chunk_operation_mismatch")
    try:
        return tuple(request.items[index] for index in chunk.item_indexes)
    except IndexError:
        raise BatchPlanningError("batch_chunk_index_invalid") from None
