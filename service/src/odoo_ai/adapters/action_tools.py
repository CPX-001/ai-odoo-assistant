"""Exact ACTION preview tool catalog and per-turn host-controlled wiring."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from contextlib import asynccontextmanager
from typing import Annotated
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from odoo_ai.application import (
    ACTION_POLICY_REVISION,
    ActionApprovalError,
    ActionApprovalService,
    ActionCreatePreviewResult,
    ActionCreatePreviewService,
    ActionPreviewError,
    ActionPreviewResult,
    ActionPreviewService,
    BusinessActionPreviewResult,
    BusinessActionPreviewService,
    EffectiveWriteSchemaError,
    EffectiveWriteSchemaResult,
    EffectiveWriteSchemaService,
    action_payload_fingerprint,
)
from odoo_ai.contracts import (
    SALE_ORDER_CONFIRM_ACTION_ID,
    SALE_ORDER_CONFIRM_SPEC_REVISION,
    ActionCreateProposalHandle,
    ActionCreateTarget,
    ActionFieldChange,
    ActionProposalHandle,
    ActionProposalPayload,
    ActionProposalPresentation,
    ActionTarget,
    ActionToolReport,
    BusinessActionProposalHandle,
    BusinessActionProposalPayload,
    ContextPack,
    EffectiveWriteSchema,
    EvidenceStatus,
    PersistActionPreviewRequest,
    RecordCreateProposalPayload,
    ToolExecutionReport,
    ToolRisk,
    ToolSpec,
    Workflow,
)
from odoo_ai.ports import OdooActionPreviewGateway
from odoo_ai.tools import (
    EvidenceLedger,
    RegisteredTool,
    ToolExecutionLimits,
    ToolExecutor,
    ToolExecutorError,
    ToolHandlerOutput,
    ToolRegistry,
)

ODOO_GET_EFFECTIVE_WRITE_SCHEMA = "odoo.get_effective_write_schema"
ODOO_PREVIEW_RECORD_PATCH = "odoo.preview_record_patch"
ODOO_PREVIEW_RECORD_CREATE = "odoo.preview_record_create"
ODOO_PREVIEW_BUSINESS_ACTION = "odoo.preview_business_action"

_EXECUTOR_IDS = {
    ODOO_GET_EFFECTIVE_WRITE_SCHEMA: "odoo.get_effective_write_schema.v1",
    ODOO_PREVIEW_RECORD_PATCH: "odoo.preview_record_patch.v1",
    ODOO_PREVIEW_RECORD_CREATE: "odoo.preview_record_create.v1",
    ODOO_PREVIEW_BUSINESS_ACTION: "odoo.preview_business_action.v1",
}
_ACTION_TOOL_RISKS = frozenset({ToolRisk.METADATA, ToolRisk.WRITE_PREVIEW})


class GetEffectiveWriteSchemaRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    model: Annotated[str, Field(pattern=r"^[A-Za-z_][A-Za-z0-9_.]{0,127}$")]


class PreviewRecordPatchRequest(BaseModel):
    """Only model/record/schema and typed bounded changes may come from Codex."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    model: Annotated[str, Field(pattern=r"^[A-Za-z_][A-Za-z0-9_.]{0,127}$")]
    record_id: int = Field(strict=True, gt=0)
    schema_id: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,31}:v[0-9]+:sha256:[0-9a-f]{64}$")
    changes: tuple[ActionFieldChange, ...] = Field(min_length=1, max_length=4)


class PreviewRecordCreateRequest(BaseModel):
    """Only an exact model/schema and bounded typed initial values may come from Codex."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    model: Annotated[str, Field(pattern=r"^[A-Za-z_][A-Za-z0-9_.]{0,127}$")]
    schema_id: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,31}:v[0-9]+:sha256:[0-9a-f]{64}$")
    values: tuple[ActionFieldChange, ...] = Field(min_length=1, max_length=4)


class PreviewBusinessActionRequest(BaseModel):
    """The only caller-controlled value is one exact host-allowlisted action id."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    action_id: Annotated[
        str,
        Field(pattern=r"^sale\.order\.confirm\.v1$", min_length=21, max_length=21),
    ]


class EffectiveWriteSchemaToolData(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    effective_schema: EffectiveWriteSchema
    evidence_id: UUID
    evidence_status: EvidenceStatus


class ActionPreviewToolData(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    proposal: ActionProposalPresentation
    evidence_status: EvidenceStatus


class ActionToolBackend:
    """Bind schema and preview to exactly one authenticated screen record."""

    def __init__(
        self,
        *,
        gateway: OdooActionPreviewGateway,
        approval_service: ActionApprovalService,
        turn_id: UUID,
        instance_id: str,
        database: str,
        uid: int,
        company_id: int,
        allowed_company_ids: tuple[int, ...],
        model: str,
        record_id: int,
        proposal_id_factory: Callable[[], UUID] = uuid4,
    ) -> None:
        self._gateway = gateway
        self._approval_service = approval_service
        self._turn_id = turn_id
        self._instance_id = instance_id
        self._database = database
        self._uid = uid
        self._company_id = company_id
        self._allowed_company_ids = allowed_company_ids
        self._model = model
        self._record_id = record_id
        self._proposal_id_factory = proposal_id_factory
        self._schema: EffectiveWriteSchemaResult | None = None
        self._proposals: list[ActionProposalPresentation] = []

    @property
    def proposals(self) -> tuple[ActionProposalPresentation, ...]:
        return tuple(self._proposals)

    async def get_effective_write_schema(
        self, request: GetEffectiveWriteSchemaRequest
    ) -> EffectiveWriteSchemaResult:
        self._require_target(request.model, self._record_id)
        if self._schema is None:
            self._schema = await EffectiveWriteSchemaService(self._gateway).get(
                model=self._model,
                instance_id=self._instance_id,
                database=self._database,
                captured_for_user=self._uid,
                company_id=self._company_id,
                allowed_company_ids=self._allowed_company_ids,
            )
        return self._schema

    async def preview_record_patch(
        self, request: PreviewRecordPatchRequest
    ) -> tuple[EffectiveWriteSchemaResult, ActionProposalHandle, ActionPreviewResult]:
        self._require_target(request.model, request.record_id)
        if self._proposals:
            raise ToolExecutorError("action_proposal_already_created")
        schema_result = await self.get_effective_write_schema(
            GetEffectiveWriteSchemaRequest(model=request.model)
        )
        if request.schema_id != schema_result.schema.schema_id:
            raise ToolExecutorError("write_schema_mismatch")
        proposal_id = self._proposal_id_factory()
        if not isinstance(proposal_id, UUID):
            raise ToolExecutorError("proposal_id_unavailable")
        payload = ActionProposalPayload(
            proposal_id=proposal_id,
            turn_id=self._turn_id,
            instance_id=self._instance_id,
            database=self._database,
            uid=self._uid,
            company_id=self._company_id,
            allowed_company_ids=self._allowed_company_ids,
            target=ActionTarget(model=self._model, record_id=self._record_id),
            changes=tuple(sorted(request.changes, key=lambda item: item.field)),
            policy_revision=schema_result.schema.policy_revision,
            schema_revision=schema_result.schema.schema_id,
        )
        fingerprint = action_payload_fingerprint(payload)
        preview_result = await ActionPreviewService(self._gateway).preview(
            payload=payload,
            payload_fingerprint=fingerprint,
            schema=schema_result.schema,
        )
        persisted = await asyncio.to_thread(
            self._approval_service.persist_preview,
            PersistActionPreviewRequest(payload=payload, preview=preview_result.preview),
        )
        if (
            persisted.proposal_id != proposal_id
            or persisted.payload_fingerprint != fingerprint
            or persisted.expires_at != preview_result.preview.expires_at
        ):
            raise ToolExecutorError("approval_store_corrupt")
        handle = ActionProposalHandle(
            proposal_id=proposal_id,
            turn_id=self._turn_id,
            payload_fingerprint=fingerprint,
            precondition_fingerprint=preview_result.preview.precondition_fingerprint,
            target=preview_result.preview.summary.target,
            changes=preview_result.preview.summary.changes,
            warnings=preview_result.preview.summary.warnings,
            expires_at=preview_result.preview.expires_at,
            evidence_id=preview_result.evidence.evidence_id,
        )
        self._proposals.append(handle)
        return schema_result, handle, preview_result

    async def preview_record_create(
        self, request: PreviewRecordCreateRequest
    ) -> tuple[EffectiveWriteSchemaResult, ActionCreateProposalHandle, ActionCreatePreviewResult]:
        self._require_target(request.model, self._record_id)
        if self._proposals:
            raise ToolExecutorError("action_proposal_already_created")
        schema_result = await self.get_effective_write_schema(
            GetEffectiveWriteSchemaRequest(model=request.model)
        )
        if request.schema_id != schema_result.schema.schema_id:
            raise ToolExecutorError("create_schema_mismatch")
        proposal_id = self._proposal_id_factory()
        if not isinstance(proposal_id, UUID):
            raise ToolExecutorError("proposal_id_unavailable")
        payload = RecordCreateProposalPayload(
            proposal_id=proposal_id,
            turn_id=self._turn_id,
            instance_id=self._instance_id,
            database=self._database,
            uid=self._uid,
            company_id=self._company_id,
            allowed_company_ids=self._allowed_company_ids,
            target=ActionCreateTarget(model=self._model),
            values=tuple(sorted(request.values, key=lambda item: item.field)),
            policy_revision=schema_result.schema.policy_revision,
            schema_revision=schema_result.schema.schema_id,
        )
        fingerprint = action_payload_fingerprint(payload)
        preview_result = await ActionCreatePreviewService(self._gateway).preview(
            payload=payload,
            payload_fingerprint=fingerprint,
            schema=schema_result.schema,
        )
        persisted = await asyncio.to_thread(
            self._approval_service.persist_preview,
            PersistActionPreviewRequest(payload=payload, preview=preview_result.preview),
        )
        if (
            persisted.proposal_id != proposal_id
            or persisted.payload_fingerprint != fingerprint
            or persisted.expires_at != preview_result.preview.expires_at
        ):
            raise ToolExecutorError("approval_store_corrupt")
        handle = ActionCreateProposalHandle(
            proposal_id=proposal_id,
            turn_id=self._turn_id,
            payload_fingerprint=fingerprint,
            precondition_fingerprint=preview_result.preview.precondition_fingerprint,
            target=preview_result.preview.summary.target,
            values=preview_result.preview.summary.values,
            warnings=preview_result.preview.summary.warnings,
            expires_at=preview_result.preview.expires_at,
            evidence_id=preview_result.evidence.evidence_id,
        )
        self._proposals.append(handle)
        return schema_result, handle, preview_result

    async def preview_business_action(
        self, request: PreviewBusinessActionRequest
    ) -> tuple[BusinessActionProposalHandle, BusinessActionPreviewResult]:
        if request.action_id != SALE_ORDER_CONFIRM_ACTION_ID:
            raise ToolExecutorError("business_action_not_allowlisted")
        self._require_target("sale.order", self._record_id)
        if self._proposals:
            raise ToolExecutorError("action_proposal_already_created")
        proposal_id = self._proposal_id_factory()
        if not isinstance(proposal_id, UUID):
            raise ToolExecutorError("proposal_id_unavailable")
        payload = BusinessActionProposalPayload(
            proposal_id=proposal_id,
            turn_id=self._turn_id,
            action_id=SALE_ORDER_CONFIRM_ACTION_ID,
            instance_id=self._instance_id,
            database=self._database,
            uid=self._uid,
            company_id=self._company_id,
            allowed_company_ids=self._allowed_company_ids,
            target=ActionTarget(model="sale.order", record_id=self._record_id),
            policy_revision=ACTION_POLICY_REVISION,
            action_spec_revision=SALE_ORDER_CONFIRM_SPEC_REVISION,
        )
        fingerprint = action_payload_fingerprint(payload)
        preview_result = await BusinessActionPreviewService(self._gateway).preview(
            payload=payload,
            payload_fingerprint=fingerprint,
        )
        persisted = await asyncio.to_thread(
            self._approval_service.persist_preview,
            PersistActionPreviewRequest(payload=payload, preview=preview_result.preview),
        )
        if (
            persisted.proposal_id != proposal_id
            or persisted.payload_fingerprint != fingerprint
            or persisted.expires_at != preview_result.preview.expires_at
        ):
            raise ToolExecutorError("approval_store_corrupt")
        summary = preview_result.preview.summary
        handle = BusinessActionProposalHandle(
            proposal_id=proposal_id,
            turn_id=self._turn_id,
            payload_fingerprint=fingerprint,
            precondition_fingerprint=preview_result.preview.precondition_fingerprint,
            target=summary.target,
            display_name=summary.display_name,
            state_before=summary.state_before,
            expected_states=summary.expected_states,
            warnings=summary.warnings,
            expires_at=preview_result.preview.expires_at,
            evidence_id=preview_result.evidence.evidence_id,
        )
        self._proposals.append(handle)
        return handle, preview_result

    def _require_target(self, model: str, record_id: int) -> None:
        if model != self._model or record_id != self._record_id:
            raise ToolExecutorError("action_target_not_allowed")


def action_tool_specs() -> tuple[ToolSpec, ...]:
    """Return the complete fixed ACTION catalog; it contains no commit operation."""

    return (
        ToolSpec(
            name=ODOO_GET_EFFECTIVE_WRITE_SCHEMA,
            description=(
                "Get the bounded effective write schema for the exact current record model. "
                "Use only returned fields and its exact schema_id."
            ),
            input_schema=GetEffectiveWriteSchemaRequest.model_json_schema(),
            risk=ToolRisk.METADATA,
            executor_id=_EXECUTOR_IDS[ODOO_GET_EFFECTIVE_WRITE_SCHEMA],
        ),
        ToolSpec(
            name=ODOO_PREVIEW_RECORD_CREATE,
            description=(
                "Create and persist an effect-free preview for one bounded record create. "
                "Use this, not record_patch, when the user requests a new record. This "
                "never creates, approves, or commits the record."
            ),
            input_schema=PreviewRecordCreateRequest.model_json_schema(),
            risk=ToolRisk.WRITE_PREVIEW,
            executor_id=_EXECUTOR_IDS[ODOO_PREVIEW_RECORD_CREATE],
        ),
        ToolSpec(
            name=ODOO_PREVIEW_RECORD_PATCH,
            description=(
                "Create and persist an effect-free preview for one typed record patch. "
                "Use only to update the exact current record; never use it for a request "
                "to create a new record. This never approves or commits the change."
            ),
            input_schema=PreviewRecordPatchRequest.model_json_schema(),
            risk=ToolRisk.WRITE_PREVIEW,
            executor_id=_EXECUTOR_IDS[ODOO_PREVIEW_RECORD_PATCH],
        ),
        ToolSpec(
            name=ODOO_PREVIEW_BUSINESS_ACTION,
            description=(
                "Preview the exact host-curated sale.order.confirm.v1 action on the "
                "current sale order. This never approves or executes the action."
            ),
            input_schema=PreviewBusinessActionRequest.model_json_schema(),
            risk=ToolRisk.WRITE_PREVIEW,
            executor_id=_EXECUTOR_IDS[ODOO_PREVIEW_BUSINESS_ACTION],
        ),
    )


def build_action_tool_registry(
    backend: ActionToolBackend,
    advertised_specs: Sequence[ToolSpec],
) -> ToolRegistry:
    bindings: list[RegisteredTool] = []
    for spec in _validated_specs(advertised_specs):
        if spec.name == ODOO_GET_EFFECTIVE_WRITE_SCHEMA:
            bindings.append(
                RegisteredTool(
                    spec=spec,
                    executor_id=spec.executor_id,
                    input_model=GetEffectiveWriteSchemaRequest,
                    output_model=EffectiveWriteSchemaToolData,
                    handler=_schema_handler(backend),
                    max_calls=1,
                    max_input_bytes=2 * 1024,
                    max_output_bytes=96 * 1024,
                )
            )
        elif spec.name == ODOO_PREVIEW_RECORD_PATCH:
            bindings.append(
                RegisteredTool(
                    spec=spec,
                    executor_id=spec.executor_id,
                    input_model=PreviewRecordPatchRequest,
                    output_model=ActionPreviewToolData,
                    handler=_preview_handler(backend),
                    max_calls=1,
                    max_input_bytes=16 * 1024,
                    max_output_bytes=96 * 1024,
                )
            )
        elif spec.name == ODOO_PREVIEW_RECORD_CREATE:
            bindings.append(
                RegisteredTool(
                    spec=spec,
                    executor_id=spec.executor_id,
                    input_model=PreviewRecordCreateRequest,
                    output_model=ActionPreviewToolData,
                    handler=_create_preview_handler(backend),
                    max_calls=1,
                    max_input_bytes=16 * 1024,
                    max_output_bytes=96 * 1024,
                )
            )
        elif spec.name == ODOO_PREVIEW_BUSINESS_ACTION:
            bindings.append(
                RegisteredTool(
                    spec=spec,
                    executor_id=spec.executor_id,
                    input_model=PreviewBusinessActionRequest,
                    output_model=ActionPreviewToolData,
                    handler=_business_preview_handler(backend),
                    max_calls=1,
                    max_input_bytes=2 * 1024,
                    max_output_bytes=96 * 1024,
                )
            )
    return ToolRegistry(bindings, allowed_risks=_ACTION_TOOL_RISKS)


def _validated_specs(advertised_specs: Sequence[ToolSpec]) -> tuple[ToolSpec, ...]:
    expected = {spec.name: spec for spec in action_tool_specs()}
    validated: list[ToolSpec] = []
    seen: set[str] = set()
    for spec in advertised_specs:
        canonical = expected.get(spec.name)
        if canonical is None:
            raise ToolExecutorError("action_tool_not_allowlisted")
        if spec.name in seen:
            raise ToolExecutorError("action_tool_duplicate")
        if spec.model_dump(mode="json") != canonical.model_dump(mode="json"):
            raise ToolExecutorError("action_tool_spec_mismatch")
        seen.add(spec.name)
        validated.append(spec)
    return tuple(validated)


def _schema_handler(
    backend: ActionToolBackend,
) -> Callable[[BaseModel], Awaitable[ToolHandlerOutput]]:
    async def handler(value: BaseModel) -> ToolHandlerOutput:
        try:
            result = await backend.get_effective_write_schema(
                GetEffectiveWriteSchemaRequest.model_validate(value)
            )
        except EffectiveWriteSchemaError as error:
            raise ToolExecutorError(error.code) from None
        data = EffectiveWriteSchemaToolData(
            effective_schema=result.schema,
            evidence_id=result.evidence.evidence_id,
            evidence_status=result.evidence.status,
        )
        return ToolHandlerOutput(data=data, evidence=(result.evidence,))

    return handler


def _preview_handler(
    backend: ActionToolBackend,
) -> Callable[[BaseModel], Awaitable[ToolHandlerOutput]]:
    async def handler(value: BaseModel) -> ToolHandlerOutput:
        try:
            schema, handle, raw = await backend.preview_record_patch(
                PreviewRecordPatchRequest.model_validate(value)
            )
            evidence = raw.evidence
        except (ActionApprovalError, ActionPreviewError, EffectiveWriteSchemaError) as error:
            raise ToolExecutorError(error.code) from None
        data = ActionPreviewToolData(
            proposal=handle,
            evidence_status=evidence.status,
        )
        return ToolHandlerOutput(
            data=data,
            evidence=(schema.evidence, evidence),
        )

    return handler


def _create_preview_handler(
    backend: ActionToolBackend,
) -> Callable[[BaseModel], Awaitable[ToolHandlerOutput]]:
    async def handler(value: BaseModel) -> ToolHandlerOutput:
        try:
            schema, handle, raw = await backend.preview_record_create(
                PreviewRecordCreateRequest.model_validate(value)
            )
            evidence = raw.evidence
        except (ActionApprovalError, ActionPreviewError, EffectiveWriteSchemaError) as error:
            raise ToolExecutorError(error.code) from None
        data = ActionPreviewToolData(
            proposal=handle,
            evidence_status=evidence.status,
        )
        return ToolHandlerOutput(data=data, evidence=(schema.evidence, evidence))

    return handler


def _business_preview_handler(
    backend: ActionToolBackend,
) -> Callable[[BaseModel], Awaitable[ToolHandlerOutput]]:
    async def handler(value: BaseModel) -> ToolHandlerOutput:
        try:
            handle, raw = await backend.preview_business_action(
                PreviewBusinessActionRequest.model_validate(value)
            )
            evidence = raw.evidence
        except (ActionApprovalError, ActionPreviewError) as error:
            raise ToolExecutorError(error.code) from None
        data = ActionPreviewToolData(
            proposal=handle,
            evidence_status=evidence.status,
        )
        return ToolHandlerOutput(data=data, evidence=(evidence,))

    return handler


class ActionToolExecutorFactory:
    """Build one preview-only registry and ledger for one p1 ACTION turn."""

    def __init__(
        self,
        *,
        gateway: OdooActionPreviewGateway,
        approval_service: ActionApprovalService,
        turn_id: UUID,
        database: str,
        user_id: int,
        company_id: int,
        allowed_company_ids: tuple[int, ...],
        model: str,
        record_id: int,
        limits: ToolExecutionLimits | None = None,
    ) -> None:
        self._gateway = gateway
        self._approval_service = approval_service
        self._turn_id = turn_id
        self._database = database
        self._user_id = user_id
        self._company_id = company_id
        self._allowed_company_ids = allowed_company_ids
        self._model = model
        self._record_id = record_id
        # Allow one bounded correction after schema discovery (for example when the
        # model initially selects patch for a create request). Every concrete ACTION
        # tool remains capped at one call and the registry still exposes no commit.
        self._limits = limits or ToolExecutionLimits(max_calls=3)
        self._last_report = ActionToolReport()

    @asynccontextmanager
    async def __call__(
        self,
        context: ContextPack,
        advertised_specs: Sequence[ToolSpec],
    ) -> AsyncIterator[ToolExecutor]:
        self._last_report = ActionToolReport()
        if (
            context.workflow_hint is not Workflow.ACTION
            or context.user.uid != self._user_id
            or context.user.company_id != self._company_id
            or tuple(context.user.allowed_company_ids) != self._allowed_company_ids
            or context.screen.model != self._model
            or context.screen.res_id != self._record_id
        ):
            raise ToolExecutorError("action_context_mismatch")
        backend = ActionToolBackend(
            gateway=self._gateway,
            approval_service=self._approval_service,
            turn_id=self._turn_id,
            instance_id=context.instance.instance_id,
            database=self._database,
            uid=self._user_id,
            company_id=self._company_id,
            allowed_company_ids=self._allowed_company_ids,
            model=self._model,
            record_id=self._record_id,
        )
        registry = build_action_tool_registry(backend, advertised_specs)
        ledger = EvidenceLedger(
            max_items=min(context.limits.max_evidence_items, self._limits.max_evidence_items),
            max_payload_bytes=self._limits.max_evidence_bytes,
            live=context.live_evidence,
            retrieved=context.retrieved_evidence,
        )
        executor = ToolExecutor(
            registry=registry,
            ledger=ledger,
            turn_limits=context.limits,
            limits=self._limits,
        )
        try:
            yield executor
        finally:
            self._last_report = ActionToolReport(
                tool_report=ToolExecutionReport(
                    events=executor.execution_events,
                    retrieved_evidence=executor.ledger.retrieved_evidence,
                ),
                proposals=backend.proposals,
            )

    def take_report(self) -> ActionToolReport:
        report = self._last_report
        self._last_report = ActionToolReport()
        return report
