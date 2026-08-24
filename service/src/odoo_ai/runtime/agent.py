"""Runtime composition for the unified agent API."""

from __future__ import annotations

import asyncio
from collections.abc import Callable

from odoo_ai.adapters.agent_tools import (
    UnifiedAgentToolExecutorFactory,
    agent_tool_policy_specs,
    agent_tool_specs,
)
from odoo_ai.adapters.batch_http import BatchOdooGatewayFactory
from odoo_ai.adapters.batch_preflight_http import BatchPreflightOdooGatewayFactory
from odoo_ai.adapters.configured_codex import ConfiguredCodexRuntimeSettings
from odoo_ai.adapters.odoo_http import (
    OdooGatewayFactory,
    OdooGatewaySettings,
)
from odoo_ai.adapters.user_model_engine import UserSelectableCodexAppServerEngine
from odoo_ai.application.action_approval import ActionApprovalService
from odoo_ai.application.action_command import ActionCommandService
from odoo_ai.application.action_execution import ActionExecutionService
from odoo_ai.application.agent_execution import AgentPlanExecutionService
from odoo_ai.application.agent_plans import AgentPlanService
from odoo_ai.application.agent_policy import intersect_agent_policy
from odoo_ai.application.agent_turn import AgentTurnService
from odoo_ai.application.batch_command import BatchCommandService
from odoo_ai.application.batch_execution import BatchMutationExecutionService
from odoo_ai.application.batch_jobs import BatchMutationJobService
from odoo_ai.contracts import ActionToolReport, AgentTurnRequest, InstanceProfileSummary
from odoo_ai.security import ActionAuthorityCodec
from odoo_ai.storage import (
    DatabaseSettings,
    SqlActionApprovalStore,
    SqlAgentPlanStore,
    SqlBatchMutationJobStore,
    create_database_engine,
    create_session_factory,
)
from odoo_ai.storage.chat_repository import ChatStoreError, recent_chat_text
from odoo_ai.storage.database import session_scope
from odoo_ai.tools import ToolExecutionLimits


class RuntimeAgentFactory:
    """Build per-turn adapters while sharing only host-owned configuration."""

    def __init__(
        self,
        *,
        database_settings: DatabaseSettings,
        gateway_factory: OdooGatewayFactory,
        instance_loader: Callable[[], InstanceProfileSummary],
        batch_preflight_factory: BatchPreflightOdooGatewayFactory | None = None,
        batch_gateway_factory: BatchOdooGatewayFactory | None = None,
    ) -> None:
        self._database_settings = database_settings
        self._gateway_factory = gateway_factory
        self._instance_loader = instance_loader
        self._batch_preflight_factory = batch_preflight_factory
        self._database_engine = create_database_engine(self._database_settings)
        sessions = create_session_factory(self._database_engine)
        action_store = SqlActionApprovalStore(sessions)
        self._approvals = ActionApprovalService(action_store)
        self._plans = AgentPlanService(SqlAgentPlanStore(sessions))
        self._batch_jobs = BatchMutationJobService(SqlBatchMutationJobStore(sessions))
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
        instance_loader: Callable[[], InstanceProfileSummary],
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
        tools = (
            agent_tool_specs(batch_enabled=self._batch_enabled)
            if allowed_models
            else ()
        )

        def report_loader() -> ActionToolReport:
            return ActionToolReport()

        tool_factory = None
        if allowed_models:
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
                limits=ToolExecutionLimits(
                    max_calls=policy.max_tool_calls_per_turn,
                    max_total_input_bytes=1024 * 1024 if self._batch_enabled else 64 * 1024,
                    per_tool_timeout_seconds=30.0 if self._batch_enabled else 5.0,
                    max_consecutive_failures=policy.max_consecutive_failures,
                ),
            )
            report_loader = tool_factory.take_report
        reasoning = UserSelectableCodexAppServerEngine(
            ConfiguredCodexRuntimeSettings.from_env(),
            tool_executor_factory=tool_factory,
        )
        return AgentTurnService(
            reasoning_engine=reasoning,
            tools=tools,
            policy_registry=agent_tool_policy_specs(
                allowed_models,
                batch_enabled=self._batch_enabled,
            ),
            plan_service=self._plans,
            execution_service=self._execution,
            report_loader=report_loader,
            history_loader=self._history,
            instance_loader=self._instance_loader,
        )

    def plan_service(self) -> AgentPlanService:
        return self._plans

    def execution_service(self) -> AgentPlanExecutionService:
        return self._execution

    async def _history(self, request: AgentTurnRequest) -> str:
        return await asyncio.to_thread(self._history_sync, request)

    def _history_sync(self, request: AgentTurnRequest) -> str:
        if request.conversation_id is None:
            return ""
        engine = create_database_engine(self._database_settings)
        try:
            sessions = create_session_factory(engine)
            with session_scope(sessions) as session:
                return recent_chat_text(
                    session,
                    actor=request.actor,
                    conversation_id=request.conversation_id,
                )
        except (ChatStoreError, OSError, RuntimeError, ValueError):
            return ""
        finally:
            engine.dispose()
