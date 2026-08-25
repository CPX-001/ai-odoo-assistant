"""Runtime composition for the unified agent API."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from time import monotonic
from typing import cast

from odoo_ai.adapters.agent_retrieval import (
    AgentRetrievalBindingFactory,
    RetrievalOnlyToolExecutorFactory,
    agent_retrieval_tool_specs,
)
from odoo_ai.adapters.agent_timing import log_agent_timing
from odoo_ai.adapters.agent_tools import (
    UnifiedAgentToolExecutorFactory,
    agent_tool_policy_specs,
    agent_tool_specs,
)
from odoo_ai.adapters.batch_http import BatchOdooGatewayFactory
from odoo_ai.adapters.batch_preflight_http import BatchPreflightOdooGatewayFactory
from odoo_ai.adapters.configured_codex import ConfiguredCodexRuntimeSettings
from odoo_ai.adapters.odoo_http import OdooGatewayFactory, OdooGatewaySettings
from odoo_ai.adapters.unified_agent_engine import UnifiedAgentCodexAppServerEngine
from odoo_ai.application.action_approval import ActionApprovalService
from odoo_ai.application.action_command import ActionCommandService
from odoo_ai.application.action_execution import ActionExecutionService
from odoo_ai.application.agent_execution import AgentPlanExecutionService
from odoo_ai.application.agent_plans import AgentPlanService
from odoo_ai.application.agent_policy import EvaluatedAgentPlan, intersect_agent_policy
from odoo_ai.application.agent_turn import AgentTurnService
from odoo_ai.application.batch_command import BatchCommandService
from odoo_ai.application.batch_execution import BatchMutationExecutionService
from odoo_ai.application.batch_jobs import BatchMutationJobService
from odoo_ai.contracts import (
    ActionToolReport,
    AgentCandidateOutput,
    AgentPlanExecutionRequest,
    AgentPlanStatusResponse,
    AgentTurnRequest,
    AgentTurnResponse,
    InstanceProfileSummary,
)
from odoo_ai.ports.agent_plans import StoredAgentPlan
from odoo_ai.security import ActionAuthorityCodec
from odoo_ai.storage import (
    DatabaseSettings,
    SqlActionApprovalStore,
    SqlAgentPlanStore,
    SqlBatchMutationJobStore,
    create_database_engine,
    create_session_factory,
    get_latest_capability_snapshot,
    get_latest_instance_profile,
)
from odoo_ai.storage.chat_repository import ChatStoreError, recent_chat_text
from odoo_ai.storage.database import session_scope
from odoo_ai.tools import ToolExecutionLimits


class RuntimeAgentFactory:
    """Build per-turn adapters while sharing host-owned database infrastructure."""

    def __init__(
        self,
        *,
        database_settings: DatabaseSettings,
        gateway_factory: OdooGatewayFactory,
        instance_loader: Callable[[], InstanceProfileSummary] | None = None,
        batch_preflight_factory: BatchPreflightOdooGatewayFactory | None = None,
        batch_gateway_factory: BatchOdooGatewayFactory | None = None,
    ) -> None:
        self._database_settings = database_settings
        self._gateway_factory = gateway_factory
        self._batch_preflight_factory = batch_preflight_factory
        self._database_engine = create_database_engine(self._database_settings)
        self._sessions = create_session_factory(self._database_engine)
        self._instance_loader = instance_loader or self._load_instance_summary_shared
        action_store = SqlActionApprovalStore(self._sessions)
        self._approvals = ActionApprovalService(action_store)
        self._plans = AgentPlanService(SqlAgentPlanStore(self._sessions))
        self._batch_jobs = BatchMutationJobService(SqlBatchMutationJobStore(self._sessions))
        self._retrieval_bindings = AgentRetrievalBindingFactory(
            sessions=self._sessions,
            inventory_gateway_loader=self._gateway_factory.for_instance,
        )
        action_execution = ActionExecutionService(
            store=action_store,
            authority_codec=ActionAuthorityCodec.from_env(),
            gateway_factory=self._gateway_factory,
        )
        commands = ActionCommandService(
            approvals=self._approvals,
            executions=action_execution,
        )
        batch_commands = None
        if batch_gateway_factory is not None:
            batch_commands = BatchCommandService(
                jobs=self._batch_jobs,
                execution=BatchMutationExecutionService(batch_gateway_factory.build()),
            )
        self._batch_enabled = (
            self._batch_preflight_factory is not None and batch_commands is not None
        )
        self._execution = AgentPlanExecutionService(
            plans=self._plans,
            actions=commands,
            batches=batch_commands if self._batch_enabled else None,
        )

    @classmethod
    def from_env(
        cls,
        *,
        gateway_factory: OdooGatewayFactory | None = None,
        instance_loader: Callable[[], InstanceProfileSummary] | None = None,
        batch_preflight_factory: BatchPreflightOdooGatewayFactory | None = None,
        batch_gateway_factory: BatchOdooGatewayFactory | None = None,
    ) -> RuntimeAgentFactory:
        settings = OdooGatewaySettings.from_env()
        return cls(
            database_settings=DatabaseSettings.from_env(),
            gateway_factory=gateway_factory or OdooGatewayFactory(settings),
            instance_loader=instance_loader,
            batch_preflight_factory=(
                batch_preflight_factory or BatchPreflightOdooGatewayFactory(settings)
            ),
            batch_gateway_factory=batch_gateway_factory or BatchOdooGatewayFactory.from_env(),
        )

    def turn_service(self, request: AgentTurnRequest) -> AgentTurnService:
        allowed_models = tuple(candidate.model for candidate in request.candidates)
        policy = intersect_agent_policy(request.policy_layers)
        retrieval_tools = agent_retrieval_tool_specs()
        limits = ToolExecutionLimits(
            max_calls=policy.max_tool_calls_per_turn,
            max_total_input_bytes=1024 * 1024 if self._batch_enabled else 64 * 1024,
            per_tool_timeout_seconds=30.0 if self._batch_enabled else 5.0,
            max_consecutive_failures=policy.max_consecutive_failures,
        )

        report_loader: Callable[[], ActionToolReport]
        tool_factory: UnifiedAgentToolExecutorFactory | RetrievalOnlyToolExecutorFactory
        if allowed_models:
            tools = (
                *agent_tool_specs(batch_enabled=self._batch_enabled),
                *retrieval_tools,
            )
            gateway = self._gateway_factory.for_turn(
                turn_id=request.turn_id,
                delegation_token=request.capability_token,
            )
            batch_preflight_gateway = None
            if self._batch_enabled:
                assert self._batch_preflight_factory is not None
                batch_preflight_gateway = self._batch_preflight_factory.for_turn(
                    turn_id=request.turn_id,
                    delegation_token=request.capability_token,
                )
            tool_factory = UnifiedAgentToolExecutorFactory(
                query_gateway=gateway,
                action_gateway=gateway,
                approval_service=self._approvals,
                turn_id=request.turn_id,
                database=request.gateway.database,
                user_id=request.user.uid,
                company_id=request.user.company_id,
                allowed_company_ids=tuple(request.user.allowed_company_ids),
                allowed_models=allowed_models,
                synthetic_data_authorized=(
                    request.synthetic_data_authorized and policy.allow_synthetic_data
                ),
                batch_preflight_gateway=batch_preflight_gateway,
                batch_job_service=self._batch_jobs if self._batch_enabled else None,
                conversation_id=request.conversation_id,
                policy_revision=policy.revision if self._batch_enabled else None,
                limits=limits,
                retrieval_binding_loader=self._retrieval_bindings,
            )
            report_loader = tool_factory.take_report
        else:
            tools = retrieval_tools
            retrieval_factory = RetrievalOnlyToolExecutorFactory(
                binding_factory=self._retrieval_bindings,
                limits=limits,
            )
            tool_factory = retrieval_factory
            report_loader = retrieval_factory.take_report

        reasoning = UnifiedAgentCodexAppServerEngine(
            ConfiguredCodexRuntimeSettings.from_env(),
            tool_executor_factory=tool_factory,
        )
        return _TimedAgentTurnService(
            reasoning_engine=reasoning,
            tools=tools,
            policy_registry=agent_tool_policy_specs(
                allowed_models,
                batch_enabled=self._batch_enabled,
            ),
            plan_service=cast(AgentPlanService, _TimedPlanCreator(self._plans)),
            execution_service=cast(
                AgentPlanExecutionService,
                _TimedExecutionService(self._execution),
            ),
            report_loader=report_loader,
            history_loader=self._history,
            instance_loader=self._timed_instance,
        )

    def plan_service(self) -> AgentPlanService:
        return self._plans

    def execution_service(self) -> AgentPlanExecutionService:
        return self._execution

    async def _history(self, request: AgentTurnRequest) -> str:
        started = monotonic()
        try:
            return await asyncio.to_thread(self._history_sync, request)
        finally:
            log_agent_timing("history_load", started)

    def _history_sync(self, request: AgentTurnRequest) -> str:
        if request.conversation_id is None:
            return ""
        try:
            with session_scope(self._sessions) as session:
                return recent_chat_text(
                    session,
                    actor=request.actor,
                    conversation_id=request.conversation_id,
                )
        except (ChatStoreError, OSError, RuntimeError, ValueError):
            return ""

    def _load_instance_summary_shared(self) -> InstanceProfileSummary:
        with session_scope(self._sessions) as session:
            profile = get_latest_instance_profile(session)
            if profile is None:
                return InstanceProfileSummary(instance_id="unknown")
            snapshot = get_latest_capability_snapshot(
                session,
                instance_profile_id=profile.id,
            )
            capabilities = (
                sorted(
                    name
                    for name, available in snapshot.capabilities.items()
                    if available
                )
                if snapshot is not None
                else []
            )
            return InstanceProfileSummary(
                instance_id=profile.instance_id,
                profile_revision=profile.fingerprint,
                capabilities=capabilities,
            )

    def _timed_instance(self) -> InstanceProfileSummary:
        started = monotonic()
        try:
            return self._instance_loader()
        finally:
            log_agent_timing("instance_context", started)


class _TimedPlanCreator:
    def __init__(self, delegate: AgentPlanService) -> None:
        self._delegate = delegate

    def create(
        self,
        *,
        request: AgentTurnRequest,
        candidate: AgentCandidateOutput,
        evaluated: EvaluatedAgentPlan,
    ) -> StoredAgentPlan:
        started = monotonic()
        try:
            return self._delegate.create(
                request=request,
                candidate=candidate,
                evaluated=evaluated,
            )
        finally:
            log_agent_timing("agent_plan_persist", started)


class _TimedExecutionService:
    def __init__(self, delegate: AgentPlanExecutionService) -> None:
        self._delegate = delegate

    async def execute(
        self,
        request: AgentPlanExecutionRequest,
    ) -> AgentPlanStatusResponse:
        started = monotonic()
        try:
            return await self._delegate.execute(request)
        finally:
            log_agent_timing("agent_write_execution", started)


class _TimedAgentTurnService(AgentTurnService):
    async def run(self, request: AgentTurnRequest) -> AgentTurnResponse:
        started = monotonic()
        try:
            return await super().run(request)
        finally:
            log_agent_timing("assistant_turn_total", started)
