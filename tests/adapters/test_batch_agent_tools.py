from __future__ import annotations

import asyncio
from uuid import UUID

from odoo_ai.adapters.batch_agent_tools import BatchToolBackend
from odoo_ai.application.batch_preflight import BatchPreflightService
from odoo_ai.contracts.action import ActionFieldChange, ActionValue, ActionValueKind
from odoo_ai.contracts.batch import (
    BatchCreateItem,
    BatchMutationKind,
    BatchMutationRequest,
)
from odoo_ai.contracts.batch_job import BatchProposalHandle
from odoo_ai.contracts.batch_preflight import BatchPreflightIssue, BatchPreflightResult
from odoo_ai.contracts.chat import ChatActor

SCHEMA_ID = "schema:v1:sha256:" + "a" * 64
JOB_FINGERPRINT = "batch-job:v1:sha256:" + "b" * 64
TURN_ID = UUID(int=21)
CONVERSATION_ID = UUID(int=22)


def _text(field: str, value: str) -> ActionFieldChange:
    return ActionFieldChange(
        field=field,
        value=ActionValue(kind=ActionValueKind.TEXT, value=value),
    )


def _request() -> BatchMutationRequest:
    return BatchMutationRequest(
        operation=BatchMutationKind.CREATE,
        model="res.partner",
        schema_id=SCHEMA_ID,
        items=(
            BatchCreateItem(source_ref="row:1", values=(_text("name", "Alpha"),)),
            BatchCreateItem(source_ref="row:2", values=(_text("name", "Rejected"),)),
            BatchCreateItem(source_ref="row:3", values=(_text("name", "Gamma"),)),
        ),
    )


class PreflightGateway:
    def __init__(self, *, reject_all: bool = False) -> None:
        self.reject_all = reject_all

    async def preflight_batch(self, request: BatchMutationRequest) -> BatchPreflightResult:
        if self.reject_all:
            return BatchPreflightResult(
                operation=request.operation,
                model=request.model,
                issues=tuple(
                    BatchPreflightIssue(
                        source_ref=item.source_ref,
                        error_code="business_rule_rejected",
                    )
                    for item in request.items
                ),
            )
        return BatchPreflightResult(
            operation=request.operation,
            model=request.model,
            accepted_source_refs=("row:1", "row:3"),
            issues=(
                BatchPreflightIssue(
                    source_ref="row:2",
                    error_code="business_rule_rejected",
                ),
            ),
        )


class CapturingJobs:
    def __init__(self) -> None:
        self.calls = []

    def prepare(self, *, spec, request):
        self.calls.append((spec, request))
        return BatchProposalHandle(
            job_id=UUID(int=23),
            turn_id=spec.turn_id,
            job_fingerprint=JOB_FINGERPRINT,
            operation=request.operation,
            model=request.model,
            item_count=len(request.items),
            failure_mode=request.failure_mode,
            source_provider=spec.source.provider,
            source_display_name=spec.source.display_name,
        )


def _backend(gateway, jobs) -> BatchToolBackend:
    return BatchToolBackend(
        preflight=BatchPreflightService(gateway),
        jobs=jobs,
        turn_id=TURN_ID,
        conversation_id=CONVERSATION_ID,
        actor=ChatActor(database="odoo-test", uid=7),
        instance_id="instance-test",
        company_id=3,
        allowed_company_ids=(3, 5),
        policy_revision="agent-policy-v3",
        allowed_models=("res.partner",),
    )


def test_preview_seals_only_accepted_rows_with_host_owned_binding() -> None:
    jobs = CapturingJobs()

    result = asyncio.run(_backend(PreflightGateway(), jobs).preview(_request()))

    assert result.accepted_count == 2
    assert result.rejected_count == 1
    assert result.proposal is not None
    assert result.proposal.item_count == 2
    assert len(jobs.calls) == 1
    spec, sealed = jobs.calls[0]
    assert tuple(item.source_ref for item in sealed.items) == ("row:1", "row:3")
    assert spec.actor == ChatActor(database="odoo-test", uid=7)
    assert spec.company_id == 3
    assert spec.allowed_company_ids == (3, 5)
    assert spec.turn_id == TURN_ID
    assert spec.conversation_id == CONVERSATION_ID
    assert spec.source.provider == "agent.turn"
    assert spec.source.reference == str(TURN_ID)
    assert spec.policy_revision == "agent-policy-v3"


def test_preview_output_does_not_echo_normalized_row_values() -> None:
    jobs = CapturingJobs()

    result = asyncio.run(_backend(PreflightGateway(), jobs).preview(_request()))
    serialized = result.model_dump_json()

    assert "Alpha" not in serialized
    assert "Gamma" not in serialized
    assert "Rejected" not in serialized
    assert "batch-job:v1:sha256:" in serialized


def test_all_rejected_rows_create_no_executable_job() -> None:
    jobs = CapturingJobs()

    result = asyncio.run(
        _backend(PreflightGateway(reject_all=True), jobs).preview(_request())
    )

    assert result.accepted_count == 0
    assert result.rejected_count == 3
    assert result.proposal is None
    assert jobs.calls == []
