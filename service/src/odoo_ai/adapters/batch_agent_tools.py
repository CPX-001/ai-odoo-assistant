"""Effect-free batch preview tool that seals only host-preflighted rows."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from odoo_ai.application.batch_jobs import BatchMutationJobService
from odoo_ai.application.batch_preflight import (
    BatchPreflightService,
    accepted_request,
)
from odoo_ai.contracts import ToolRisk, ToolSpec
from odoo_ai.contracts.batch import BatchMutationRequest
from odoo_ai.contracts.batch_job import (
    BatchMutationJobSpec,
    BatchProposalHandle,
    BatchProposalTrace,
)
from odoo_ai.contracts.batch_preflight import BatchPreflightIssue
from odoo_ai.contracts.chat import ChatActor
from odoo_ai.contracts.content_source import ContentSourceDescriptor
from odoo_ai.tools import RegisteredTool, ToolExecutorError, ToolHandlerOutput

ODOO_PREVIEW_BATCH_MUTATION = "odoo.preview_batch_mutation"
_BATCH_EXECUTOR_ID = "odoo.preview_batch_mutation.v1"
MAX_BATCH_ISSUE_PREVIEW = 50


class BatchPreviewToolData(BaseModel):
    """Compact model-visible result; normalized row payloads are deliberately omitted."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    proposal: BatchProposalHandle | None = None
    accepted_count: int = Field(strict=True, ge=0, le=500)
    rejected_count: int = Field(strict=True, ge=0, le=500)
    issues: tuple[BatchPreflightIssue, ...] = Field(
        default=(), max_length=MAX_BATCH_ISSUE_PREVIEW
    )
    issues_truncated: bool = False

    @model_validator(mode="after")
    def validate_summary(self) -> Self:
        if (self.proposal is None) != (self.accepted_count == 0):
            raise ValueError("batch preview proposal count is inconsistent")
        if self.proposal is not None and self.proposal.item_count != self.accepted_count:
            raise ValueError("batch preview proposal count is inconsistent")
        if len(self.issues) > self.rejected_count:
            raise ValueError("batch preview issue count is inconsistent")
        if self.issues_truncated != (len(self.issues) < self.rejected_count):
            raise ValueError("batch preview truncation marker is inconsistent")
        if self.accepted_count + self.rejected_count < 1:
            raise ValueError("batch preview cannot be empty")
        return self


class BatchToolBackend:
    """Bind normalized batch preview to one real Odoo actor and one agent turn."""

    def __init__(
        self,
        *,
        preflight: BatchPreflightService,
        jobs: BatchMutationJobService,
        turn_id: UUID,
        conversation_id: UUID | None,
        actor: ChatActor,
        instance_id: str,
        company_id: int,
        allowed_company_ids: tuple[int, ...],
        policy_revision: str,
        allowed_models: Sequence[str],
    ) -> None:
        self._preflight = preflight
        self._jobs = jobs
        self._turn_id = turn_id
        self._conversation_id = conversation_id
        self._actor = actor
        self._instance_id = instance_id
        self._company_id = company_id
        self._allowed_company_ids = allowed_company_ids
        self._policy_revision = policy_revision
        self._allowed_models = set(allowed_models)
        self._proposals: list[BatchProposalHandle] = []
        self._traces: list[BatchProposalTrace] = []

    @property
    def proposals(self) -> tuple[BatchProposalHandle, ...]:
        return tuple(self._proposals)

    @property
    def traces(self) -> tuple[BatchProposalTrace, ...]:
        return tuple(self._traces)

    def allow_models(self, models: Sequence[str]) -> None:
        self._allowed_models.update(models)

    async def preview(self, request: BatchMutationRequest) -> BatchPreviewToolData:
        if request.model not in self._allowed_models:
            raise ToolExecutorError("action_target_not_allowed")
        if len(self._proposals) >= 12:
            raise ToolExecutorError("batch_proposal_limit_exceeded")
        try:
            result = await self._preflight.preflight(request)
            accepted = accepted_request(request, result)
        except Exception as error:
            code = str(getattr(error, "code", "batch_preflight_unavailable"))
            raise ToolExecutorError(code) from None

        handle = None
        if accepted is not None:
            spec = BatchMutationJobSpec(
                turn_id=self._turn_id,
                conversation_id=self._conversation_id,
                actor=self._actor,
                instance_id=self._instance_id,
                company_id=self._company_id,
                allowed_company_ids=self._allowed_company_ids,
                operation=accepted.operation,
                model=accepted.model,
                schema_id=accepted.schema_id,
                failure_mode=accepted.failure_mode,
                policy_revision=self._policy_revision,
                source=ContentSourceDescriptor(
                    provider="agent.turn",
                    reference=str(self._turn_id),
                    display_name="Agent turn batch",
                ),
            )
            try:
                handle = await asyncio.to_thread(
                    self._jobs.prepare,
                    spec=spec,
                    request=accepted,
                )
            except Exception as error:
                code = str(getattr(error, "code", "batch_job_store_unavailable"))
                raise ToolExecutorError(code) from None
            trace = BatchProposalTrace(
                tool_name=ODOO_PREVIEW_BATCH_MUTATION,
                arguments=handle.model_dump(mode="json"),
                job_id=handle.job_id,
                job_fingerprint=handle.job_fingerprint,
            )
            self._proposals.append(handle)
            self._traces.append(trace)

        issue_preview = result.issues[:MAX_BATCH_ISSUE_PREVIEW]
        return BatchPreviewToolData(
            proposal=handle,
            accepted_count=len(result.accepted_source_refs),
            rejected_count=len(result.issues),
            issues=issue_preview,
            issues_truncated=len(issue_preview) < len(result.issues),
        )


def batch_tool_spec() -> ToolSpec:
    return ToolSpec(
        name=ODOO_PREVIEW_BATCH_MUTATION,
        description=(
            "Validate and prepare a bounded bulk create, uniform patch, or delete against "
            "the real Odoo user. This tool never commits. For create/patch, first obtain "
            "the effective write schema and use its exact schema_id. source_ref values "
            "must uniquely identify the normalized rows."
        ),
        input_schema=BatchMutationRequest.model_json_schema(),
        risk=ToolRisk.WRITE_PREVIEW,
        executor_id=_BATCH_EXECUTOR_ID,
    )


def build_batch_tool_binding(
    backend: BatchToolBackend,
    advertised_spec: ToolSpec,
) -> RegisteredTool:
    canonical = batch_tool_spec()
    if advertised_spec.model_dump(mode="json") != canonical.model_dump(mode="json"):
        raise ToolExecutorError("agent_tool_spec_mismatch")

    async def handler(value: BaseModel) -> ToolHandlerOutput:
        if not isinstance(value, BatchMutationRequest):
            raise ToolExecutorError("tool_input_invalid")
        result = await backend.preview(value)
        return ToolHandlerOutput(data=result)

    return RegisteredTool(
        spec=advertised_spec,
        executor_id=_BATCH_EXECUTOR_ID,
        input_model=BatchMutationRequest,
        output_model=BatchPreviewToolData,
        handler=handler,
        max_calls=4,
        max_input_bytes=512 * 1024,
        max_output_bytes=128 * 1024,
    )
