from __future__ import annotations

import pytest
from odoo_ai.application.batching import (
    BatchPlannerLimits,
    BatchPlanningError,
    chunk_items,
    plan_batch_mutation,
)
from odoo_ai.contracts.action import ActionFieldChange, ActionValue, ActionValueKind
from odoo_ai.contracts.batch import (
    BatchCreateItem,
    BatchDeleteItem,
    BatchFailureMode,
    BatchMutationKind,
    BatchMutationRequest,
    BatchPatchItem,
)
from pydantic import ValidationError

SCHEMA_ID = "schema:v1:sha256:" + "a" * 64


def _text(field: str, value: str) -> ActionFieldChange:
    return ActionFieldChange(
        field=field,
        value=ActionValue(kind=ActionValueKind.TEXT, value=value),
    )


def _integer(field: str, value: int) -> ActionFieldChange:
    return ActionFieldChange(
        field=field,
        value=ActionValue(kind=ActionValueKind.INTEGER, value=value),
    )


def test_batch_defaults_to_continue_on_error() -> None:
    request = BatchMutationRequest(
        operation=BatchMutationKind.DELETE,
        model="sale.order",
        items=(BatchDeleteItem(source_ref="row:1", record_id=1),),
    )

    assert request.failure_mode is BatchFailureMode.CONTINUE_ON_ERROR


def test_create_batches_use_conservative_multi_create_chunks() -> None:
    request = BatchMutationRequest(
        operation=BatchMutationKind.CREATE,
        model="res.partner",
        schema_id=SCHEMA_ID,
        items=tuple(
            BatchCreateItem(source_ref=f"row:{index}", values=(_text("name", f"P {index}"),))
            for index in range(121)
        ),
    )

    plan = plan_batch_mutation(request)

    assert plan.total_items == 121
    assert plan.estimated_orm_calls == 3
    assert tuple(len(chunk.item_indexes) for chunk in plan.chunks) == (50, 50, 21)
    assert chunk_items(request, plan.chunks[-1])[-1].source_ref == "row:120"


def test_delete_batches_are_larger_recordset_operations() -> None:
    request = BatchMutationRequest(
        operation=BatchMutationKind.DELETE,
        model="sale.order",
        items=tuple(
            BatchDeleteItem(source_ref=f"row:{index}", record_id=index + 1)
            for index in range(205)
        ),
    )

    plan = plan_batch_mutation(request)

    assert plan.estimated_orm_calls == 3
    assert tuple(len(chunk.item_indexes) for chunk in plan.chunks) == (100, 100, 5)


def test_patch_groups_identical_assignments_for_recordset_write() -> None:
    common_a = (_text("state", "draft"), _integer("priority", 1))
    # Reversed field order must still be recognized as the same assignment.
    common_b = (_integer("priority", 1), _text("state", "draft"))
    request = BatchMutationRequest(
        operation=BatchMutationKind.PATCH,
        model="x.batch.demo",
        schema_id=SCHEMA_ID,
        items=(
            BatchPatchItem(source_ref="row:1", record_id=1, changes=common_a),
            BatchPatchItem(source_ref="row:2", record_id=2, changes=(_text("state", "done"),)),
            BatchPatchItem(source_ref="row:3", record_id=3, changes=common_b),
            BatchPatchItem(source_ref="row:4", record_id=4, changes=(_text("state", "done"),)),
        ),
    )

    plan = plan_batch_mutation(request)

    assert plan.estimated_orm_calls == 2
    assert plan.chunks[0].item_indexes == (0, 2)
    assert plan.chunks[1].item_indexes == (1, 3)
    assert all(chunk.uniform_values for chunk in plan.chunks)


def test_patch_grouping_still_respects_chunk_limit() -> None:
    request = BatchMutationRequest(
        operation=BatchMutationKind.PATCH,
        model="x.batch.demo",
        schema_id=SCHEMA_ID,
        items=tuple(
            BatchPatchItem(
                source_ref=f"row:{index}",
                record_id=index + 1,
                changes=(_text("state", "done"),),
            )
            for index in range(23)
        ),
    )

    plan = plan_batch_mutation(
        request,
        limits=BatchPlannerLimits(patch_chunk_size=10),
    )

    assert tuple(len(chunk.item_indexes) for chunk in plan.chunks) == (10, 10, 3)


def test_batch_contract_rejects_duplicate_targets_and_missing_schema() -> None:
    with pytest.raises(ValidationError):
        BatchMutationRequest(
            operation=BatchMutationKind.DELETE,
            model="sale.order",
            items=(
                BatchDeleteItem(source_ref="row:1", record_id=7),
                BatchDeleteItem(source_ref="row:2", record_id=7),
            ),
        )

    with pytest.raises(ValidationError):
        BatchMutationRequest(
            operation=BatchMutationKind.CREATE,
            model="res.partner",
            items=(BatchCreateItem(source_ref="row:1", values=(_text("name", "A"),)),),
        )


def test_host_chunk_limits_are_bounded() -> None:
    with pytest.raises(BatchPlanningError, match="invalid_batch_chunk_size"):
        BatchPlannerLimits(create_chunk_size=201)
