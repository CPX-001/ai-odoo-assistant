"""Explicit QUERY dynamic-tool catalog and per-turn executor wiring."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from contextlib import asynccontextmanager
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from odoo_ai.application.effective_schema import (
    EffectiveSchemaError,
    EffectiveSchemaResult,
)
from odoo_ai.application.query_primitives import (
    AggregateRecordsExecution,
    QueryPrimitiveError,
    QueryPrimitiveService,
    QueryRecordsExecution,
)
from odoo_ai.contracts import (
    AggregateRecordsRequest,
    AggregateRecordsResult,
    ContextPack,
    EffectiveModelSchema,
    EvidenceStatus,
    QueryRecordsRequest,
    QueryRecordsResult,
    ToolExecutionReport,
    ToolRisk,
    ToolSpec,
)
from odoo_ai.ports import OdooQueryGateway
from odoo_ai.tools import (
    EvidenceLedger,
    RegisteredTool,
    ToolExecutionLimits,
    ToolExecutor,
    ToolExecutorError,
    ToolHandlerOutput,
    ToolRegistry,
)

ODOO_GET_EFFECTIVE_SCHEMA = "odoo.get_effective_schema"
ODOO_QUERY_RECORDS = "odoo.query_records"
ODOO_AGGREGATE_RECORDS = "odoo.aggregate_records"

_EXECUTOR_IDS = {
    ODOO_GET_EFFECTIVE_SCHEMA: "odoo.get_effective_schema.v1",
    ODOO_QUERY_RECORDS: "odoo.query_records.v1",
    ODOO_AGGREGATE_RECORDS: "odoo.aggregate_records.v1",
}


class GetEffectiveSchemaRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    model: Annotated[str, Field(pattern=r"^[A-Za-z_][A-Za-z0-9_.]{0,127}$")]


class EffectiveSchemaToolData(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    effective_schema: EffectiveModelSchema
    evidence_id: UUID
    evidence_status: EvidenceStatus


class QueryRecordsToolData(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    result: QueryRecordsResult
    evidence_id: UUID
    evidence_status: EvidenceStatus


class AggregateRecordsToolData(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    result: AggregateRecordsResult
    evidence_id: UUID
    evidence_status: EvidenceStatus


def query_tool_specs() -> tuple[ToolSpec, ...]:
    """Return the complete fixed read-only QUERY catalog."""

    return (
        ToolSpec(
            name=ODOO_GET_EFFECTIVE_SCHEMA,
            description=(
                "Get the bounded runtime schema for one host-authorized Odoo model under the "
                "authenticated Odoo user. The current screen is only context and need not "
                "match this model. Use its exact schema_id and fields in subsequent QUERY "
                "calls. Field visibility comes from Odoo, not from model assumptions."
            ),
            input_schema=GetEffectiveSchemaRequest.model_json_schema(),
            risk=ToolRisk.METADATA,
            executor_id=_EXECUTOR_IDS[ODOO_GET_EFFECTIVE_SCHEMA],
        ),
        ToolSpec(
            name=ODOO_QUERY_RECORDS,
            description=(
                "Search and read bounded Odoo records with a flat typed filter, structured "
                "sort, and the exact effective schema_id. The target model may differ from "
                "the current screen when the host authorized or dynamically discovered it. "
                "The host already executes as the authenticated Odoo user and applies Odoo "
                "ACLs, record rules, field access, and active-company context. Never add "
                "owner, salesperson, assigned-user, user_id, or create_uid filters as an "
                "authorization measure; use ownership filters only when the user's business "
                "question explicitly requests them."
            ),
            input_schema=QueryRecordsRequest.model_json_schema(),
            risk=ToolRisk.READ,
            executor_id=_EXECUTOR_IDS[ODOO_QUERY_RECORDS],
        ),
        ToolSpec(
            name=ODOO_AGGREGATE_RECORDS,
            description=(
                "Run bounded count/sum/min/max aggregation as the authenticated Odoo user. "
                "The target model may differ from the current screen. Odoo itself applies "
                "ACLs, record rules, field access, and active-company context. Never narrow "
                "by owner, salesperson, assigned user, user_id, or create_uid merely to "
                "emulate permissions; apply such filters only when the user explicitly asks "
                "for that business scope."
            ),
            input_schema=AggregateRecordsRequest.model_json_schema(),
            risk=ToolRisk.READ,
            executor_id=_EXECUTOR_IDS[ODOO_AGGREGATE_RECORDS],
        ),
    )


class QueryToolBackend:
    """Bind primitives to host-authorized models and the effective user."""

    def __init__(
        self,
        service: QueryPrimitiveService,
        *,
        user_id: int,
        model: str | None = None,
        allowed_models: Sequence[str] = (),
    ) -> None:
        self._service = service
        self._user_id = user_id
        self._model = model
        self._allowed_models = set(allowed_models or (() if model is None else (model,)))
        self._schemas: dict[str, EffectiveSchemaResult] = {}

    async def get_effective_schema(
        self, request: GetEffectiveSchemaRequest
    ) -> EffectiveSchemaResult:
        self._require_model(request.model)
        if request.model not in self._schemas:
            self._schemas[request.model] = await self._service.get_effective_schema(
                model=request.model,
                captured_for_user=self._user_id,
            )
        return self._schemas[request.model]

    async def query_records(
        self, request: QueryRecordsRequest
    ) -> tuple[EffectiveSchemaResult, QueryRecordsExecution]:
        self._require_model(request.model)
        schema = await self.get_effective_schema(GetEffectiveSchemaRequest(model=request.model))
        result = await self._service.query_records(request, schema=schema.schema)
        return schema, result

    async def aggregate_records(
        self, request: AggregateRecordsRequest
    ) -> tuple[EffectiveSchemaResult, AggregateRecordsExecution]:
        self._require_model(request.model)
        schema = await self.get_effective_schema(GetEffectiveSchemaRequest(model=request.model))
        result = await self._service.aggregate_records(request, schema=schema.schema)
        return schema, result

    def _require_model(self, model: str) -> None:
        if model not in self._allowed_models:
            raise ToolExecutorError("query_model_not_allowed")

    def allow_models(self, models: Sequence[str]) -> None:
        self._allowed_models.update(models)


def build_query_tool_registry(
    backend: QueryToolBackend,
    advertised_specs: Sequence[ToolSpec],
) -> ToolRegistry:
    bindings: list[RegisteredTool] = []
    for spec in _validated_specs(advertised_specs):
        if spec.name == ODOO_GET_EFFECTIVE_SCHEMA:
            bindings.append(
                RegisteredTool(
                    spec=spec,
                    executor_id=spec.executor_id,
                    input_model=GetEffectiveSchemaRequest,
                    output_model=EffectiveSchemaToolData,
                    handler=_schema_handler(backend),
                    max_calls=12,
                    max_input_bytes=2 * 1024,
                    max_output_bytes=96 * 1024,
                )
            )
        elif spec.name == ODOO_QUERY_RECORDS:
            bindings.append(
                RegisteredTool(
                    spec=spec,
                    executor_id=spec.executor_id,
                    input_model=QueryRecordsRequest,
                    output_model=QueryRecordsToolData,
                    handler=_records_handler(backend),
                    max_calls=12,
                    max_input_bytes=16 * 1024,
                    max_output_bytes=128 * 1024,
                )
            )
        elif spec.name == ODOO_AGGREGATE_RECORDS:
            bindings.append(
                RegisteredTool(
                    spec=spec,
                    executor_id=spec.executor_id,
                    input_model=AggregateRecordsRequest,
                    output_model=AggregateRecordsToolData,
                    handler=_aggregate_handler(backend),
                    max_calls=12,
                    max_input_bytes=16 * 1024,
                    max_output_bytes=128 * 1024,
                )
            )
    return ToolRegistry(bindings)


def _validated_specs(advertised_specs: Sequence[ToolSpec]) -> tuple[ToolSpec, ...]:
    expected = {spec.name: spec for spec in query_tool_specs()}
    validated: list[ToolSpec] = []
    seen: set[str] = set()
    for spec in advertised_specs:
        canonical = expected.get(spec.name)
        if canonical is None:
            raise ToolExecutorError("query_tool_not_allowlisted")
        if spec.name in seen:
            raise ToolExecutorError("query_tool_duplicate")
        if spec.model_dump(mode="json") != canonical.model_dump(mode="json"):
            raise ToolExecutorError("query_tool_spec_mismatch")
        seen.add(spec.name)
        validated.append(spec)
    return tuple(validated)


def _schema_handler(
    backend: QueryToolBackend,
) -> Callable[[BaseModel], Awaitable[ToolHandlerOutput]]:
    async def handler(value: BaseModel) -> ToolHandlerOutput:
        try:
            result = await backend.get_effective_schema(
                GetEffectiveSchemaRequest.model_validate(value)
            )
        except (EffectiveSchemaError, QueryPrimitiveError) as error:
            raise ToolExecutorError(error.code) from None
        data = EffectiveSchemaToolData(
            effective_schema=result.schema,
            evidence_id=result.evidence.evidence_id,
            evidence_status=result.evidence.status,
        )
        return ToolHandlerOutput(data=data.model_dump(mode="json"), evidence=(result.evidence,))

    return handler


def _records_handler(
    backend: QueryToolBackend,
) -> Callable[[BaseModel], Awaitable[ToolHandlerOutput]]:
    async def handler(value: BaseModel) -> ToolHandlerOutput:
        try:
            schema, execution = await backend.query_records(
                QueryRecordsRequest.model_validate(value)
            )
        except (EffectiveSchemaError, QueryPrimitiveError) as error:
            raise ToolExecutorError(error.code) from None
        data = QueryRecordsToolData(
            result=execution.result,
            evidence_id=execution.evidence.evidence_id,
            evidence_status=execution.evidence.status,
        )
        return ToolHandlerOutput(
            data=data.model_dump(mode="json"),
            evidence=(schema.evidence, execution.evidence),
        )

    return handler


def _aggregate_handler(
    backend: QueryToolBackend,
) -> Callable[[BaseModel], Awaitable[ToolHandlerOutput]]:
    async def handler(value: BaseModel) -> ToolHandlerOutput:
        try:
            schema, execution = await backend.aggregate_records(
                AggregateRecordsRequest.model_validate(value)
            )
        except (EffectiveSchemaError, QueryPrimitiveError) as error:
            raise ToolExecutorError(error.code) from None
        data = AggregateRecordsToolData(
            result=execution.result,
            evidence_id=execution.evidence.evidence_id,
            evidence_status=execution.evidence.status,
        )
        return ToolHandlerOutput(
            data=data.model_dump(mode="json"),
            evidence=(schema.evidence, execution.evidence),
        )

    return handler


class QueryToolExecutorFactory:
    """Build one QUERY registry, ledger, and executor for one q1 product turn."""

    def __init__(
        self,
        *,
        gateway: OdooQueryGateway,
        user_id: int,
        model: str,
        limits: ToolExecutionLimits | None = None,
    ) -> None:
        self._gateway = gateway
        self._user_id = user_id
        self._model = model
        self._limits = limits or ToolExecutionLimits()
        self._last_report = ToolExecutionReport()

    @asynccontextmanager
    async def __call__(
        self,
        context: ContextPack,
        advertised_specs: Sequence[ToolSpec],
    ) -> AsyncIterator[ToolExecutor]:
        self._last_report = ToolExecutionReport()
        if context.user.uid != self._user_id or context.screen.model != self._model:
            raise ToolExecutorError("query_context_mismatch")
        registry = build_query_tool_registry(
            QueryToolBackend(
                QueryPrimitiveService(self._gateway),
                user_id=self._user_id,
                model=self._model,
            ),
            advertised_specs,
        )
        ledger = EvidenceLedger(
            max_items=min(
                context.limits.max_evidence_items,
                self._limits.max_evidence_items,
            ),
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
            self._last_report = ToolExecutionReport(
                events=executor.execution_events,
                retrieved_evidence=executor.ledger.retrieved_evidence,
            )

    def take_report(self) -> ToolExecutionReport:
        report = self._last_report
        self._last_report = ToolExecutionReport()
        return report
