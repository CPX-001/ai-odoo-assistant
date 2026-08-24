"""Unified turn orchestration with deterministic host-side authority."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID

from odoo_ai.application.agent_execution import (
    AgentExecutionError,
    AgentPlanExecutionService,
)
from odoo_ai.application.agent_plans import AgentPlanError, AgentPlanService, agent_plan_view
from odoo_ai.application.agent_policy import (
    AgentPolicyError,
    AgentProposalBinding,
    EvaluatedAgentPlan,
    evaluate_agent_candidate,
    intersect_agent_policy,
)
from odoo_ai.application.context_read import (
    Clock,
    ContextReadError,
    InstanceLoader,
    validate_agent_turn_request,
)
from odoo_ai.contracts import (
    ActionToolReport,
    AgentCandidateOutput,
    AgentPlanExecutionRequest,
    AgentTurnRequest,
    AgentTurnResponse,
    ConfirmationMode,
    ContextPack,
    ConversationState,
    HostToolPolicySpec,
    InstanceProfileSummary,
    PlanState,
    RiskLevel,
    ToolSpec,
    TurnLimits,
    UserRequest,
)
from odoo_ai.ports import AgentReasoningEngine

AgentHistoryLoader = Callable[[AgentTurnRequest], str | Awaitable[str]]
AgentReportLoader = Callable[[], ActionToolReport]

_READ_TOOLS = frozenset(
    {"odoo.get_effective_schema", "odoo.query_records", "odoo.aggregate_records"}
)
_SCHEMA_TOOLS = frozenset(
    {
        "odoo.search_models",
        "odoo.get_effective_schema",
        "odoo.get_effective_write_schema",
    }
)
_PREVIEW_TOOLS = frozenset(
    {
        "odoo.preview_record_patch",
        "odoo.preview_record_create",
        "odoo.preview_business_action",
        "odoo.preview_record_archive",
        "odoo.preview_record_delete",
        "odoo.preview_sale_order_build_flow",
    }
)


class AgentTurnError(RuntimeError):
    def __init__(self, code: str, status_code: int = 422) -> None:
        super().__init__(code)
        self.code = code
        self.status_code = status_code


class AgentTurnService:
    """Let reasoning read and preview, then let the host validate and persist the plan."""

    def __init__(
        self,
        *,
        reasoning_engine: AgentReasoningEngine,
        tools: Sequence[ToolSpec],
        policy_registry: Sequence[HostToolPolicySpec],
        plan_service: AgentPlanService,
        execution_service: AgentPlanExecutionService | None = None,
        report_loader: AgentReportLoader = lambda: ActionToolReport(),
        history_loader: AgentHistoryLoader = lambda request: "",
        instance_loader: InstanceLoader = lambda: InstanceProfileSummary(
            instance_id="unknown"
        ),
        clock: Clock = lambda: datetime.now(UTC),
    ) -> None:
        self._reasoning_engine = reasoning_engine
        self._tools = tuple(ToolSpec.model_validate(tool) for tool in tools)
        self._policy_registry = tuple(
            HostToolPolicySpec.model_validate(spec) for spec in policy_registry
        )
        self._plan_service = plan_service
        self._execution_service = execution_service
        self._report_loader = report_loader
        self._history_loader = history_loader
        self._instance_loader = instance_loader
        self._clock = clock

    async def run(self, request: AgentTurnRequest) -> AgentTurnResponse:
        report_taken = False
        try:
            now = self._now()
            validate_agent_turn_request(request, now=now)
            if request.user.allowed_company_ids != sorted(request.user.allowed_company_ids):
                raise AgentTurnError("invalid_user_context")
            policy = intersect_agent_policy(request.policy_layers)
            history = await _maybe_await_history(self._history_loader, request)
            instance = self._instance()
            capabilities = list(instance.capabilities)
            capabilities.extend(
                [
                    "host_owns_approval",
                    "host_scope_explicit_all_resolved",
                    "host_clarification_material_data_only",
                    _autonomy_capability(policy.confirmation_mode, policy.max_auto_risk),
                ]
            )
            if request.synthetic_data_authorized and policy.allow_synthetic_data:
                capabilities.append("synthetic_test_data_allowed")
            context = ContextPack(
                request=UserRequest(message=request.message),
                screen=request.screen,
                user=request.user,
                workflow_hint=None,
                instance=instance.model_copy(
                    update={"capabilities": sorted(set(capabilities))}
                ),
                conversation_state=ConversationState(
                    current_screen=request.screen,
                    short_summary=history[:8_000],
                ),
                limits=TurnLimits(
                    max_tool_calls=policy.max_tool_calls_per_turn,
                    max_evidence_items=24,
                ),
            )
            candidate = await self._reasoning_engine.run_agent_turn(
                context,
                list(self._tools),
            )
            report = self._report_loader()
            report_taken = True
            candidate, bindings = _reconcile_previews(
                candidate,
                report,
                turn_id=request.turn_id,
            )
            evaluated = evaluate_agent_candidate(
                candidate,
                registry=self._policy_registry,
                layers=request.policy_layers,
                proposal_bindings=bindings,
            )
            evaluated = _merge_observed_metadata(evaluated, report)
            plan = await asyncio.to_thread(
                self._plan_service.create,
                request=request,
                candidate=candidate,
                evaluated=evaluated,
            )
            if plan.state is PlanState.AUTHORIZED:
                if self._execution_service is None:
                    raise AgentTurnError("agent_execution_unavailable", 503)
                status = await self._execution_service.execute(
                    AgentPlanExecutionRequest(
                        plan_id=plan.plan_id,
                        actor=request.actor,
                    )
                )
                state = status.plan.state
                view = status.plan
            else:
                state = plan.state
                view = agent_plan_view(plan)
            response = AgentTurnResponse(
                turn_id=request.turn_id,
                conversation_id=request.conversation_id,
                state=state,
                answer_markdown=candidate.answer_markdown,
                confidence=candidate.confidence,
                plan=view,
                completed_at=self._now(),
            )
            secret = request.capability_token.get_secret_value()
            if secret and secret in response.model_dump_json():
                raise AgentTurnError("unsafe_response", 502)
            return response
        except AgentTurnError:
            raise
        except ContextReadError as error:
            raise AgentTurnError(error.code, error.status_code) from None
        except AgentPolicyError as error:
            raise AgentTurnError(error.code, 422) from None
        except AgentPlanError as error:
            raise AgentTurnError(error.code, error.status_code) from None
        except AgentExecutionError as error:
            raise AgentTurnError(error.code, error.status_code) from None
        except Exception as error:
            code = str(getattr(error, "code", "agent_engine_unavailable"))
            if "timeout" in code or "deadline" in code:
                raise AgentTurnError("agent_engine_timeout", 504) from None
            if "budget" in code or "limit" in code or "repeated" in code:
                raise AgentTurnError(code, 422) from None
            raise AgentTurnError("agent_engine_unavailable", 503) from None
        finally:
            if not report_taken:
                try:
                    self._report_loader()
                except Exception:
                    pass

    def _now(self) -> datetime:
        value = self._clock()
        if not isinstance(value, datetime) or value.tzinfo is None:
            raise AgentTurnError("clock_unavailable", 503)
        return value.astimezone(UTC)

    def _instance(self) -> InstanceProfileSummary:
        try:
            value = self._instance_loader()
        except Exception:
            return InstanceProfileSummary(instance_id="unknown")
        return (
            value
            if isinstance(value, InstanceProfileSummary)
            else InstanceProfileSummary(instance_id="unknown")
        )


def _autonomy_capability(mode: ConfirmationMode, risk: RiskLevel) -> str:
    if mode is ConfirmationMode.ALWAYS_CONFIRM:
        return "host_autonomy:strict"
    if mode is ConfirmationMode.PROTECTED_ONLY and risk is RiskLevel.PROTECTED:
        return "host_autonomy:full_access"
    if mode is ConfirmationMode.PROTECTED_ONLY:
        return "host_autonomy:autonomous"
    return "host_autonomy:balanced"


async def _maybe_await_history(
    loader: AgentHistoryLoader,
    request: AgentTurnRequest,
) -> str:
    value = loader(request)
    if asyncio.iscoroutine(value):
        value = await value
    return value if isinstance(value, str) else ""


def _reconcile_previews(
    candidate: AgentCandidateOutput,
    report: ActionToolReport,
    *,
    turn_id: UUID,
) -> tuple[AgentCandidateOutput, Mapping[str, AgentProposalBinding]]:
    if len(report.proposals) != len(report.proposal_traces):
        raise AgentTurnError("agent_preview_report_corrupt", 502)
    if len(candidate.steps) != len(report.proposal_traces):
        raise AgentTurnError("agent_preview_plan_mismatch", 502)
    bindings: dict[str, AgentProposalBinding] = {}
    normalized_steps = []
    for step, trace in zip(candidate.steps, report.proposal_traces, strict=True):
        if trace.tool_name not in _PREVIEW_TOOLS:
            raise AgentTurnError("agent_preview_report_corrupt", 502)
        proposal = next(
            (
                item
                for item in report.proposals
                if item.proposal_id == trace.proposal_id
                and item.payload_fingerprint == trace.payload_fingerprint
            ),
            None,
        )
        if proposal is None or proposal.turn_id != turn_id:
            raise AgentTurnError("agent_preview_report_corrupt", 502)
        bindings[step.step_id] = AgentProposalBinding(
            proposal_id=trace.proposal_id,
            payload_fingerprint=trace.payload_fingerprint,
        )
        normalized_steps.append(
            step.model_copy(
                update={
                    "tool_name": trace.tool_name,
                    "arguments": trace.arguments,
                }
            )
        )
    return candidate.model_copy(update={"steps": tuple(normalized_steps)}), bindings


def _merge_observed_metadata(
    evaluated: EvaluatedAgentPlan,
    report: ActionToolReport,
) -> EvaluatedAgentPlan:
    observed_tools = {
        str(event.attributes.get("tool_name"))
        for event in report.tool_report.events
        if event.event_name == "tool.completed" and event.status == "ok"
    }
    metadata = evaluated.metadata.model_copy(
        update={
            "needs_read": evaluated.metadata.needs_read
            or bool(observed_tools.intersection(_READ_TOOLS)),
            "needs_schema": evaluated.metadata.needs_schema
            or bool(observed_tools.intersection(_SCHEMA_TOOLS)),
        }
    )
    return replace(evaluated, metadata=metadata)
