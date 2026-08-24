from __future__ import annotations

import asyncio
from uuid import UUID

import pytest

from odoo_ai.application.batch_execution import (
    BatchExecutionError,
    BatchMutationExecutionService,
)
from odoo_ai.application.batching import BatchPlannerLimits
from odoo_ai.contracts.action import ActionFieldChange, ActionValue, ActionValueKind
from odoo_ai.contracts.batch import (
    BatchCreateItem,
    BatchDeleteItem,
    BatchFailureMode,
    BatchItemResult,
    BatchItemState,
    BatchMutationKind,
    BatchMutationRequest,
    BatchPatchItem,
)
from odoo_ai.contracts.batch_job import BatchExecutionContext

SCHEMA_ID = "schema:v1:sha256:" + "b" * 64
JOB_FINGERPRINT = "batch-job:v1:sha256:" + "c" * 64
CONTEXT = BatchExecutionContext(
    job_id=UUID(int=10),
    attempt_id=UUID(int=11),
    authorization_id=UUID(int=12),
    job_fingerprint=JOB_FINGERPRINT,
    instance_id="instance-test",
    database="odoo-test",
    uid=7,
    company_id=1,
    allowed_company_ids=(1,),
    policy_revision="agent-policy-v3",
)


def _text(field: str, value: str) -> ActionFieldChange:
    return ActionFieldChange(
        field=field,
        value=ActionValue(kind=ActionValueKind.TEXT, value=value),
    )


class FakeBatchGateway:
    def __init__(self, *, fail_refs=()) -> None:
        self.fail_refs = set(fail_refs)
        self.calls = []
        self.next_id = 1000

    def _results(self, items, *, created: bool = False):
        results = []
        for item in items:
            if item.source_ref in self.fail_refs:
                results.append(
                    BatchItemResult(
                        source_ref=item.source_ref,
                        state=BatchItemState.FAILED,
                        error_code="row_rejected",
                    )
                )
                continue
            record_id = getattr(item, "record_id", None)
            if created:
                self.next_id += 1
                record_id = self.next_id
            results.append(
                BatchItemResult(
                    source_ref=item.source_ref,
                    state=BatchItemState.APPLIED,
                    record_id=record_id,
                )
            )
        return tuple(results)

    async def create_many(self, *, context, model, schema_id, items, failure_mode):
        self.calls.append(("create", model, schema_id, len(items), failure_mode, context))
        return self._results(items, created=True)

    async def patch_many(self, *, context, model, schema_id, items, failure_mode):
        self.calls.append(("patch", model, schema_id, len(items), failure_mode, context))
        return self._results(items)

    async def delete_many(self, *, context, model, items, failure_mode):
        self.calls.append(("delete", model, None, len(items), failure_mode, context))
        return self._results(items)


def test_one_failed_row_does_not_stop_later_chunks() -> None:
    gateway = FakeBatchGateway(fail_refs={"row:17"})
    service = BatchMutationExecutionService(
        gateway,
        limits=BatchPlannerLimits(delete_chunk_size=10),
    )
    request = BatchMutationRequest(
        operation=BatchMutationKind.DELETE,
        model="sale.order",
        items=tuple(
            BatchDeleteItem(source_ref=f"row:{index}", record_id=index + 1)
            for index in range(25)
        ),
    )

    result = asyncio.run(service.execute(request, context=CONTEXT))

    assert result.total_items == 25
    assert result.applied_items == 24
    assert result.failed_items == 1
    assert result.results[17].state is BatchItemState.FAILED
    assert result.results[18].state is BatchItemState.APPLIED
    assert [call[3] for call in gateway.calls] == [10, 10, 5]
    assert all(call[4] is BatchFailureMode.CONTINUE_ON_ERROR for call in gateway.calls)
    assert all(call[5] == CONTEXT for call in gateway.calls)


def test_create_results_keep_source_row_to_created_record_mapping() -> None:
    gateway = FakeBatchGateway(fail_refs={"sheet1:3"})
    service = BatchMutationExecutionService(gateway)
    request = BatchMutationRequest(
        operation=BatchMutationKind.CREATE,
        model="res.partner",
        schema_id=SCHEMA_ID,
        items=(
            BatchCreateItem(source_ref="sheet1:2", values=(_text("name", "A"),)),
            BatchCreateItem(source_ref="sheet1:3", values=(_text("name", "B"),)),
            BatchCreateItem(source_ref="sheet1:4", values=(_text("name", "C"),)),
        ),
    )

    result = asyncio.run(service.execute(request, context=CONTEXT))

    assert tuple(item.source_ref for item in result.results) == (
        "sheet1:2",
        "sheet1:3",
        "sheet1:4",
    )
    assert result.results[0].record_id is not None
    assert result.results[1].error_code == "row_rejected"
    assert result.results[2].record_id is not None


def test_patch_planner_grouping_is_used_by_execution_service() -> None:
    gateway = FakeBatchGateway()
    service = BatchMutationExecutionService(gateway)
    request = BatchMutationRequest(
        operation=BatchMutationKind.PATCH,
        model="res.partner",
        schema_id=SCHEMA_ID,
        items=(
            BatchPatchItem(
                source_ref="row:1",
                record_id=1,
                changes=(_text("city", "Barcelona"),),
            ),
            BatchPatchItem(
                source_ref="row:2",
                record_id=2,
                changes=(_text("city", "Madrid"),),
            ),
            BatchPatchItem(
                source_ref="row:3",
                record_id=3,
                changes=(_text("city", "Barcelona"),),
            ),
        ),
    )

    result = asyncio.run(service.execute(request, context=CONTEXT))

    assert result.applied_items == 3
    assert [call[3] for call in gateway.calls] == [2, 1]


class CorruptBatchGateway(FakeBatchGateway):
    async def delete_many(self, *, context, model, items, failure_mode):
        del context, model, failure_mode
        return (
            BatchItemResult(
                source_ref=items[0].source_ref,
                state=BatchItemState.APPLIED,
                record_id=items[0].record_id,
            ),
        )


def test_gateway_must_return_exactly_one_result_per_row() -> None:
    service = BatchMutationExecutionService(CorruptBatchGateway())
    request = BatchMutationRequest(
        operation=BatchMutationKind.DELETE,
        model="sale.order",
        items=(
            BatchDeleteItem(source_ref="row:1", record_id=1),
            BatchDeleteItem(source_ref="row:2", record_id=2),
        ),
    )

    with pytest.raises(BatchExecutionError, match="batch_gateway_result_corrupt"):
        asyncio.run(service.execute(request, context=CONTEXT))
