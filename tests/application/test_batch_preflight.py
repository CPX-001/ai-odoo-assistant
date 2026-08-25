from __future__ import annotations

import asyncio

import pytest
from odoo_ai.application.batch_preflight import (
    BatchPreflightError,
    BatchPreflightService,
    accepted_request,
)
from odoo_ai.contracts.batch import (
    BatchDeleteItem,
    BatchMutationKind,
    BatchMutationRequest,
)
from odoo_ai.contracts.batch_preflight import BatchPreflightIssue, BatchPreflightResult


class FakePreflightGateway:
    def __init__(self, rejected: set[str] | None = None) -> None:
        self.rejected = rejected or set()
        self.calls: list[BatchMutationRequest] = []

    async def preflight_batch(self, request: BatchMutationRequest) -> BatchPreflightResult:
        self.calls.append(request)
        accepted = tuple(
            item.source_ref for item in request.items if item.source_ref not in self.rejected
        )
        issues = tuple(
            BatchPreflightIssue(source_ref=item.source_ref, error_code="row_rejected")
            for item in request.items
            if item.source_ref in self.rejected
        )
        return BatchPreflightResult(
            operation=request.operation,
            model=request.model,
            accepted_source_refs=accepted,
            issues=issues,
        )


def _delete_request(count: int) -> BatchMutationRequest:
    return BatchMutationRequest(
        operation=BatchMutationKind.DELETE,
        model="res.partner",
        items=tuple(
            BatchDeleteItem(source_ref=f"row:{index}", record_id=index + 1)
            for index in range(count)
        ),
    )


def test_preflight_chunks_500_rows_by_50_and_preserves_source_order() -> None:
    request = _delete_request(500)
    rejected = {"row:0", "row:49", "row:50", "row:499"}
    gateway = FakePreflightGateway(rejected)

    result = asyncio.run(BatchPreflightService(gateway).preflight(request))

    assert [len(call.items) for call in gateway.calls] == [50] * 10
    assert result.accepted_source_refs[0] == "row:1"
    assert result.accepted_source_refs[-1] == "row:498"
    assert tuple(issue.source_ref for issue in result.issues) == (
        "row:0",
        "row:49",
        "row:50",
        "row:499",
    )


def test_accepted_request_keeps_exact_original_rows_and_order() -> None:
    request = _delete_request(5)
    result = BatchPreflightResult(
        operation=BatchMutationKind.DELETE,
        model="res.partner",
        accepted_source_refs=("row:1", "row:3"),
        issues=(
            BatchPreflightIssue(source_ref="row:0", error_code="row_rejected"),
            BatchPreflightIssue(source_ref="row:2", error_code="row_rejected"),
            BatchPreflightIssue(source_ref="row:4", error_code="row_rejected"),
        ),
    )

    accepted = accepted_request(request, result)

    assert accepted is not None
    assert tuple(item.source_ref for item in accepted.items) == ("row:1", "row:3")
    assert tuple(item.record_id for item in accepted.items) == (2, 4)


def test_corrupt_gateway_partition_is_rejected_closed() -> None:
    request = _delete_request(2)

    class CorruptGateway:
        async def preflight_batch(self, chunk):
            return BatchPreflightResult(
                operation=chunk.operation,
                model=chunk.model,
                accepted_source_refs=(chunk.items[0].source_ref,),
            )

    with pytest.raises(BatchPreflightError, match="batch_preflight_result_corrupt"):
        asyncio.run(BatchPreflightService(CorruptGateway()).preflight(request))


def test_gateway_model_mismatch_is_rejected_closed() -> None:
    request = _delete_request(1)

    class WrongModelGateway:
        async def preflight_batch(self, chunk):
            return BatchPreflightResult(
                operation=chunk.operation,
                model="crm.lead",
                accepted_source_refs=(chunk.items[0].source_ref,),
            )

    with pytest.raises(BatchPreflightError, match="batch_preflight_result_corrupt"):
        asyncio.run(BatchPreflightService(WrongModelGateway()).preflight(request))
