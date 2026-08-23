"""Opt-in real Codex QUERY turn using the production dynamic-tool registry."""

import asyncio
import os
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from odoo_ai.adapters import (
    CodexAppServerEngine,
    CodexRuntimeSettings,
    QueryToolExecutorFactory,
    query_tool_specs,
)
from odoo_ai.application import QueryService
from odoo_ai.contracts import (
    AggregateRecordsRequest,
    AggregateRecordsResult,
    Evidence,
    EvidenceKind,
    EvidenceSensitivity,
    EvidenceStatus,
    QueryRecordsRequest,
    QueryRecordsResult,
    QueryTurnRequest,
)


class SyntheticQueryGateway:
    async def get_query_model_metadata(self, model: str) -> Evidence:
        return Evidence(
            evidence_id=uuid4(),
            kind=EvidenceKind.METADATA,
            status=EvidenceStatus.CHECKED,
            title="Synthetic schema",
            summary="Checked runtime-shaped metadata.",
            payload={
                "model": model,
                "label": "Synthetic Order",
                "fields": {
                    "name": {
                        "groupable": True,
                        "readonly": True,
                        "required": True,
                        "searchable": True,
                        "sortable": True,
                        "string": "Number",
                        "type": "char",
                    }
                },
            },
            pointer={"model": model, "provider": "synthetic"},
            observed_at=datetime.now(UTC),
            sensitivity=EvidenceSensitivity.TECHNICAL,
        )

    async def query_records(self, request: QueryRecordsRequest) -> QueryRecordsResult:
        return QueryRecordsResult(
            model=request.model,
            schema_id=request.schema_id,
            query=request,
            records=(),
            returned_count=0,
            limit=request.limit,
            truncated=False,
            captured_at=datetime.now(UTC),
        )

    async def aggregate_records(
        self, request: AggregateRecordsRequest
    ) -> AggregateRecordsResult:
        del request
        raise AssertionError("aggregate tool was not requested")


@pytest.mark.skipif(
    not os.environ.get("ODOO_AI_RUN_CODEX_QUERY_SMOKE"),
    reason="real authenticated Codex QUERY smoke is opt-in",
)
def test_real_codex_completes_checked_empty_query_turn() -> None:
    gateway = SyntheticQueryGateway()
    factory = QueryToolExecutorFactory(
        gateway=gateway,
        user_id=17,
        model="sale.order",
    )
    engine = CodexAppServerEngine(
        CodexRuntimeSettings.from_env(),
        tool_executor_factory=factory,
    )
    service = QueryService(
        reasoning_engine=engine,
        query_tools=query_tool_specs(),
        report_loader=factory.take_report,
    )
    now = datetime.now(UTC)
    request = QueryTurnRequest.model_validate(
        {
            "turn_id": str(uuid4()),
            "message": (
                "Call odoo.get_effective_schema for sale.order, then call "
                "odoo.query_records with that exact schema_id, field name, no "
                "conditions or order, and limit 1. Answer that the checked result "
                "is empty, use workflow QUERY, and cite the query Evidence id."
            ),
            "screen": {
                "view_type": "list",
                "model": "sale.order",
                "captured_at": now.isoformat(),
            },
            "user": {
                "uid": 17,
                "company_id": 3,
                "allowed_company_ids": [3],
            },
            "delegation_token": "q1." + "d" * 256,
            "gateway": {"database": "synthetic"},
        }
    )

    response = asyncio.run(service.run(request))

    assert response.workflow.value == "QUERY"
    assert response.citations[0].empty is True
    assert response.citations[0].returned_count == 0
