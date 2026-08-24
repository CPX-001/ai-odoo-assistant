"""Unified read and preview-only tool registry for one agent turn."""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from odoo_ai.adapters.action_tools import (
    ODOO_GET_EFFECTIVE_WRITE_SCHEMA,
    ODOO_PREVIEW_BUSINESS_ACTION,
    ODOO_PREVIEW_RECORD_ARCHIVE,
    ODOO_PREVIEW_RECORD_CREATE,
    ODOO_PREVIEW_RECORD_DELETE,
    ODOO_PREVIEW_RECORD_PATCH,
    ODOO_PREVIEW_SALE_ORDER_BUILD_FLOW,
    ActionToolBackend,
    action_tool_specs,
    build_action_tool_registry,
)
from odoo_ai.adapters.query_tools import (
    ODOO_AGGREGATE_RECORDS,
    ODOO_GET_EFFECTIVE_SCHEMA,
    ODOO_QUERY_RECORDS,
    QueryToolBackend,
    build_query_tool_registry,
    query_tool_specs,
)
from odoo_ai.application.action_approval import ActionApprovalService
from odoo_ai.application.query_primitives import QueryPrimitiveService
from odoo_ai.contracts import (
    ActionToolReport,
    AgentModelSearchRequest,
    AgentModelSearchResult,
    ContextPack,
    EffectScope,
    HostToolPolicySpec,
    RiskLevel,
    ToolExecutionReport,
    ToolRisk,
    ToolSpec,
)
from odoo_ai.ports import OdooActionPreviewGateway, OdooQueryGateway
from odoo_ai.tools import (
    EvidenceLedger,
    RegisteredTool,
    ToolExecutionLimits,
    ToolExecutor,
    ToolExecutorError,
    ToolHandlerOutput,
    ToolRegistry,
)

_AGENT_TOOL_RISKS = frozenset(
    {ToolRisk.READ, ToolRisk.METADATA, ToolRisk.WRITE_PREVIEW, ToolRisk.ACTION_PREVIEW}
)
ODOO_SEARCH_MODELS = "odoo.search_models"
_SEARCH_MODELS_EXECUTOR_ID = "odoo.search_models.v1"


class AgentModelSearchToolData(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    result: AgentModelSearchResult


def agent_tool_specs() -> tuple[ToolSpec, ...]:
    return (
        ToolSpec(
            name=ODOO_SEARCH_MODELS,
            description=(
                "Search the actual installed Odoo model registry under the authenticated "
                "user. Use this before guessing a model name, including for OCA, custom, "
                "or third-party modules. Results grant no access by themselves."
            ),
            input_schema=AgentModelSearchRequest.model_json_schema(),
            risk=ToolRisk.METADATA,
            executor_id=_SEARCH_MODELS_EXECUTOR_ID,
        ),
        *query_tool_specs(),
        *action_tool_specs(),
    )


def agent_tool_policy_specs(allowed_models: Sequence[str]) -> tuple[HostToolPolicySpec, ...]:
    models = tuple(dict.fromkeys(allowed_models))
    return (
        HostToolPolicySpec(
            tool_name=ODOO_SEARCH_MODELS,
            is_write=False,
            needs_schema=True,
            effect_scope=EffectScope.READ_ONLY,
            risk_floor=RiskLevel.LOW,
            atomic=True,
            max_records=0,
            allowed_models=(),
        ),
        HostToolPolicySpec(
            tool_name=ODOO_GET_EFFECTIVE_SCHEMA,
            is_write=False,
            needs_schema=True,
            effect_scope=EffectScope.READ_ONLY,
            risk_floor=RiskLevel.LOW,
            atomic=True,
            max_records=0,
            allowed_models=(),
        ),
        HostToolPolicySpec(
            tool_name=ODOO_QUERY_RECORDS,
            is_write=False,
            effect_scope=EffectScope.READ_ONLY,
            risk_floor=RiskLevel.LOW,
            atomic=True,
            max_records=0,
            allowed_models=(),
        ),
        HostToolPolicySpec(
            tool_name=ODOO_AGGREGATE_RECORDS,
            is_write=False,
            effect_scope=EffectScope.READ_ONLY,
            risk_floor=RiskLevel.LOW,
            atomic=True,
            max_records=0,
            allowed_models=(),
        ),
        HostToolPolicySpec(
            tool_name=ODOO_GET_EFFECTIVE_WRITE_SCHEMA,
            is_write=False,
            needs_schema=True,
            effect_scope=EffectScope.READ_ONLY,
            risk_floor=RiskLevel.LOW,
            atomic=True,
            max_records=0,
            allowed_models=(),
        ),
        HostToolPolicySpec(
            tool_name=ODOO_PREVIEW_RECORD_PATCH,
            is_write=True,
            needs_schema=True,
            effect_scope=EffectScope.INTERNAL_REVERSIBLE,
            risk_floor=RiskLevel.LOW,
            atomic=True,
            max_records=1,
            allowed_models=(),
        ),
        HostToolPolicySpec(
            tool_name=ODOO_PREVIEW_RECORD_CREATE,
            is_write=True,
            needs_schema=True,
            effect_scope=EffectScope.INTERNAL_REVERSIBLE,
            risk_floor=RiskLevel.LOW,
            atomic=True,
            max_records=1,
            allowed_models=(),
        ),
        HostToolPolicySpec(
            tool_name=ODOO_PREVIEW_BUSINESS_ACTION,
            is_write=True,
            is_business_action=True,
            effect_scope=EffectScope.INTERNAL_REVERSIBLE,
            risk_floor=RiskLevel.MODERATE,
            atomic=True,
            max_records=3,
            allowed_models=("sale.order",) if "sale.order" in models else (),
        ),
        HostToolPolicySpec(
            tool_name=ODOO_PREVIEW_RECORD_ARCHIVE,
            is_write=True,
            is_business_action=True,
            effect_scope=EffectScope.INTERNAL_REVERSIBLE,
            risk_floor=RiskLevel.MODERATE,
            atomic=True,
            max_records=1,
            allowed_models=(),
        ),
        HostToolPolicySpec(
            tool_name=ODOO_PREVIEW_RECORD_DELETE,
            is_write=True,
            is_business_action=True,
            effect_scope=EffectScope.INTERNAL_IRREVERSIBLE,
            risk_floor=RiskLevel.PROTECTED,
            atomic=True,
            max_records=1,
            allowed_models=(),
        ),
        HostToolPolicySpec(
            tool_name=ODOO_PREVIEW_SALE_ORDER_BUILD_FLOW,
            is_write=True,
            is_business_action=True,
            effect_scope=EffectScope.INTERNAL_REVERSIBLE,
            risk_floor=RiskLevel.LOW,
            atomic=True,
            max_records=3,
            allowed_models=(),
        ),
    )


class UnifiedAgentToolExecutorFactory:
    """Compose query and write-preview handlers without exposing any commit handler."""

    def __init__(
        self,
        *,
        query_gateway: OdooQueryGateway,
        action_gateway: OdooActionPreviewGateway,
        approval_service: ActionApprovalService,
        turn_id: UUID,
        database: str,
        user_id: int,
        company_id: int,
        allowed_company_ids: tuple[int, ...],
        allowed_models: Sequence[str],
        synthetic_data_authorized: bool = False,
        limits: ToolExecutionLimits | None = None,
    ) -> None:
        self._query_gateway = query_gateway
        self._action_gateway = action_gateway
        self._approval_service = approval_service
        self._turn_id = turn_id
        self._database = database
        self._user_id = user_id
        self._company_id = company_id
        self._allowed_company_ids = allowed_company_ids
        self._allowed_models = tuple(dict.fromkeys(allowed_models))
        self._synthetic_data_authorized = synthetic_data_authorized
        self._limits = limits or ToolExecutionLimits(
            max_calls=32,
            max_consecutive_failures=3,
        )
        self._last_report = ActionToolReport()

    @asynccontextmanager
    async def __call__(
        self,
        context: ContextPack,
        advertised_specs: Sequence[ToolSpec],
    ) -> AsyncIterator[ToolExecutor]:
        self._last_report = ActionToolReport()
        if (
            context.workflow_hint is not None
            or context.user.uid != self._user_id
            or context.user.company_id != self._company_id
            or tuple(context.user.allowed_company_ids) != self._allowed_company_ids
            or not self._allowed_models
        ):
            raise ToolExecutorError("agent_context_mismatch")
        advertised = {spec.name: spec for spec in advertised_specs}
        query_specs = tuple(
            advertised[name]
            for name in (ODOO_GET_EFFECTIVE_SCHEMA, ODOO_QUERY_RECORDS, ODOO_AGGREGATE_RECORDS)
            if name in advertised
        )
        action_specs = tuple(
            advertised[name]
            for name in (
                ODOO_GET_EFFECTIVE_WRITE_SCHEMA,
                ODOO_PREVIEW_RECORD_CREATE,
                ODOO_PREVIEW_RECORD_PATCH,
                ODOO_PREVIEW_BUSINESS_ACTION,
                ODOO_PREVIEW_RECORD_ARCHIVE,
                ODOO_PREVIEW_RECORD_DELETE,
                ODOO_PREVIEW_SALE_ORDER_BUILD_FLOW,
            )
            if name in advertised
        )
        query_backend = QueryToolBackend(
            QueryPrimitiveService(self._query_gateway),
            user_id=self._user_id,
            allowed_models=self._allowed_models,
        )
        default_model = context.screen.model or self._allowed_models[0]
        action_backend = ActionToolBackend(
            gateway=self._action_gateway,
            approval_service=self._approval_service,
            turn_id=self._turn_id,
            instance_id=context.instance.instance_id,
            database=self._database,
            uid=self._user_id,
            company_id=self._company_id,
            allowed_company_ids=self._allowed_company_ids,
            model=default_model,
            record_id=context.screen.res_id,
            allowed_models=self._allowed_models,
            restrict_record_target=False,
            synthetic_data_authorized=self._synthetic_data_authorized,
        )
        search_spec = advertised.get(ODOO_SEARCH_MODELS)
        search_bindings: list[RegisteredTool] = []
        if search_spec is not None:
            canonical_search = agent_tool_specs()[0]
            if search_spec.model_dump(mode="json") != canonical_search.model_dump(mode="json"):
                raise ToolExecutorError("agent_tool_spec_mismatch")

            async def search_handler(value: BaseModel) -> ToolHandlerOutput:
                search_request = AgentModelSearchRequest.model_validate(value)
                result = await self._query_gateway.search_agent_models(search_request)
                discovered = tuple(item.model for item in result.models)
                query_backend.allow_models(discovered)
                action_backend.allow_models(discovered)
                return ToolHandlerOutput(
                    data=AgentModelSearchToolData(result=result),
                    changes_preconditions=bool(discovered),
                )

            search_bindings.append(
                RegisteredTool(
                    spec=search_spec,
                    executor_id=search_spec.executor_id,
                    input_model=AgentModelSearchRequest,
                    output_model=AgentModelSearchToolData,
                    handler=search_handler,
                    max_calls=4,
                    max_input_bytes=2 * 1024,
                    max_output_bytes=32 * 1024,
                )
            )
        bindings = [
            *search_bindings,
            *build_query_tool_registry(query_backend, query_specs).bindings,
            *build_action_tool_registry(action_backend, action_specs).bindings,
        ]
        registry = ToolRegistry(bindings, allowed_risks=_AGENT_TOOL_RISKS)
        if registry.specs != tuple(advertised_specs):
            raise ToolExecutorError("agent_tool_registry_mismatch")
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
                proposals=action_backend.proposals,
                proposal_traces=action_backend.proposal_traces,
            )

    def take_report(self) -> ActionToolReport:
        report = self._last_report
        self._last_report = ActionToolReport()
        return report
