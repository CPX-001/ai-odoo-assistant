"""Chunk normalized rows through an effect-free Odoo preflight gateway."""

from __future__ import annotations

from odoo_ai.contracts.batch import BatchMutationRequest
from odoo_ai.contracts.batch_preflight import (
    BatchPreflightIssue,
    BatchPreflightResult,
)
from odoo_ai.ports.batch_preflight import BatchPreflightGateway

MAX_PREFLIGHT_ROWS_PER_CALL = 50


class BatchPreflightError(RuntimeError):
    def __init__(self, code: str, status_code: int = 409) -> None:
        super().__init__(code)
        self.code = code
        self.status_code = status_code


class BatchPreflightService:
    """Validate up to one durable job while keeping each Odoo call tightly bounded."""

    def __init__(
        self,
        gateway: BatchPreflightGateway,
        *,
        max_rows_per_call: int = MAX_PREFLIGHT_ROWS_PER_CALL,
    ) -> None:
        if type(max_rows_per_call) is not int or not 1 <= max_rows_per_call <= 50:
            raise BatchPreflightError("batch_preflight_limit_invalid", 503)
        self._gateway = gateway
        self._max_rows_per_call = max_rows_per_call

    async def preflight(self, request: BatchMutationRequest) -> BatchPreflightResult:
        accepted: set[str] = set()
        issues: dict[str, BatchPreflightIssue] = {}
        items = request.items
        for offset in range(0, len(items), self._max_rows_per_call):
            chunk_items = items[offset : offset + self._max_rows_per_call]
            chunk = BatchMutationRequest(
                operation=request.operation,
                model=request.model,
                schema_id=request.schema_id,
                failure_mode=request.failure_mode,
                items=chunk_items,
            )
            try:
                result = await self._gateway.preflight_batch(chunk)
            except BatchPreflightError:
                raise
            except Exception as error:
                code = str(getattr(error, "code", "batch_preflight_unavailable"))
                status = int(getattr(error, "status_code", 503))
                raise BatchPreflightError(code, status) from None
            _validate_chunk_result(chunk, result)
            accepted.update(result.accepted_source_refs)
            issues.update((issue.source_ref, issue) for issue in result.issues)

        ordered_accepted = tuple(
            item.source_ref for item in items if item.source_ref in accepted
        )
        ordered_issues = tuple(
            issues[item.source_ref] for item in items if item.source_ref in issues
        )
        return BatchPreflightResult(
            operation=request.operation,
            model=request.model,
            accepted_source_refs=ordered_accepted,
            issues=ordered_issues,
        )


def accepted_request(
    request: BatchMutationRequest,
    result: BatchPreflightResult,
) -> BatchMutationRequest | None:
    """Filter a preflighted request without changing row order or row payloads."""

    if result.operation is not request.operation or result.model != request.model:
        raise BatchPreflightError("batch_preflight_result_corrupt", 502)
    accepted = set(result.accepted_source_refs)
    items = tuple(item for item in request.items if item.source_ref in accepted)
    if not items:
        return None
    if len(items) != len(accepted):
        raise BatchPreflightError("batch_preflight_result_corrupt", 502)
    return BatchMutationRequest(
        operation=request.operation,
        model=request.model,
        schema_id=request.schema_id,
        failure_mode=request.failure_mode,
        items=items,
    )


def _validate_chunk_result(
    request: BatchMutationRequest,
    result: BatchPreflightResult,
) -> None:
    if result.operation is not request.operation or result.model != request.model:
        raise BatchPreflightError("batch_preflight_result_corrupt", 502)
    expected = tuple(item.source_ref for item in request.items)
    actual = tuple(result.accepted_source_refs) + tuple(
        issue.source_ref for issue in result.issues
    )
    if len(actual) != len(expected) or set(actual) != set(expected):
        raise BatchPreflightError("batch_preflight_result_corrupt", 502)
