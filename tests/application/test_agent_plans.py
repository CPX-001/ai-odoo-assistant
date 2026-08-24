from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID

from odoo_ai.application.agent_plans import AgentPlanService
from odoo_ai.application.agent_policy import evaluate_agent_candidate
from odoo_ai.application.agent_turn import _reconcile_previews
from odoo_ai.contracts import (
    ActionProposalTrace,
    ActionToolReport,
    AgentCandidateOutput,
    AgentCandidateStep,
    AgentModelCandidate,
    AgentPlanDecisionRequest,
    AgentPolicyLayer,
    AgentPolicyLayers,
    AgentTurnRequest,
    AuthorizationSource,
    BusinessActionProposalHandle,
    ConfirmationMode,
    EffectScope,
    HostToolPolicySpec,
    OdooGatewayReference,
    PlanState,
    RiskLevel,
    ScreenContext,
    UserExecutionContext,
)
from odoo_ai.contracts.chat import ChatActor
from odoo_ai.ports.agent_plans import (
    AgentPlanTransitionOutcome,
    AgentPlanTransitionResult,
    StoredAgentPlan,
)

NOW = datetime(2026, 8, 24, 12, 0, tzinfo=UTC)
PLAN_ID = UUID("10000000-0000-4000-8000-000000000001")
AUTH_ID = UUID("10000000-0000-4000-8000-000000000002")


class MemoryPlanStore:
    def __init__(self) -> None:
        self.plan: StoredAgentPlan | None = None

    def create(self, plan: StoredAgentPlan) -> None:
        self.plan = plan

    def get(self, plan_id: UUID) -> StoredAgentPlan | None:
        return self.plan if self.plan and self.plan.plan_id == plan_id else None

    def decide(
        self,
        *,
        plan_id: UUID,
        actor: ChatActor,
        approve: bool,
        authorization_id: UUID | None,
        decided_at: datetime,
    ) -> AgentPlanTransitionResult:
        if self.plan is None or self.plan.plan_id != plan_id:
            return AgentPlanTransitionResult(AgentPlanTransitionOutcome.NOT_FOUND)
        if self.plan.actor != actor:
            return AgentPlanTransitionResult(AgentPlanTransitionOutcome.BINDING_MISMATCH)
        if self.plan.state is not PlanState.AWAITING_CONFIRMATION:
            return AgentPlanTransitionResult(AgentPlanTransitionOutcome.INVALID_STATE)
        self.plan = replace(
            self.plan,
            state=PlanState.AUTHORIZED if approve else PlanState.REJECTED,
            authorization_id=authorization_id,
            authorization_source=(
                AuthorizationSource.USER_CONFIRMATION if approve else None
            ),
            decided_by_uid=actor.uid,
            decided_at=decided_at,
            updated_at=decided_at,
        )
        return AgentPlanTransitionResult(AgentPlanTransitionOutcome.APPLIED, self.plan)

    def claim_execution(self, **kwargs):  # pragma: no cover - protocol fixture
        raise NotImplementedError

    def complete(self, **kwargs):  # pragma: no cover - protocol fixture
        raise NotImplementedError


def _policy_layers(max_auto_risk: RiskLevel = RiskLevel.LOW) -> AgentPolicyLayers:
    permissive = AgentPolicyLayer(
        confirmation_mode=ConfirmationMode.PROTECTED_ONLY,
        max_auto_risk=RiskLevel.HIGH,
    )
    return AgentPolicyLayers(
        system_ceiling=permissive,
        administrator=permissive,
        user=AgentPolicyLayer(
            confirmation_mode=ConfirmationMode.RISK_BASED,
            max_auto_risk=max_auto_risk,
        ),
        conversation=permissive,
    )


def _request(layers: AgentPolicyLayers) -> AgentTurnRequest:
    return AgentTurnRequest(
        turn_id=UUID("20000000-0000-4000-8000-000000000001"),
        actor=ChatActor(database="odoo", uid=7),
        message="Crea y confirma un presupuesto de prueba",
        screen=ScreenContext(captured_at=NOW),
        user=UserExecutionContext(uid=7, company_id=1, allowed_company_ids=[1]),
        gateway=OdooGatewayReference(database="odoo"),
        capability_token="opaque",
        candidates=(AgentModelCandidate(model="sale.order"),),
        policy_layers=layers,
    )


def _candidate() -> AgentCandidateOutput:
    return AgentCandidateOutput(
        answer_markdown="Crearé y confirmaré el presupuesto de prueba.",
        confidence="high",
        assumptions=("Se usarán datos marcados como AI TEST.",),
        steps=(
            AgentCandidateStep(
                step_id="sale_flow",
                title="Crear y confirmar presupuesto",
                tool_name="sale.order.build_flow.v1",
                arguments={"model": "sale.order", "end_state": "sale_order"},
            ),
        ),
    )


def _evaluated(layers: AgentPolicyLayers):
    return evaluate_agent_candidate(
        _candidate(),
        registry=(
            HostToolPolicySpec(
                tool_name="sale.order.build_flow.v1",
                is_write=True,
                is_business_action=True,
                effect_scope=EffectScope.INTERNAL_REVERSIBLE,
                risk_floor=RiskLevel.MODERATE,
                atomic=True,
                max_records=3,
                allowed_models=("sale.order",),
            ),
        ),
        layers=layers,
    )


def test_create_persists_one_immutable_grouped_plan_awaiting_confirmation() -> None:
    store = MemoryPlanStore()
    ids = iter((PLAN_ID, AUTH_ID))
    service = AgentPlanService(store, clock=lambda: NOW, id_factory=lambda: next(ids))
    layers = _policy_layers()

    plan = service.create(
        request=_request(layers),
        candidate=_candidate(),
        evaluated=_evaluated(layers),
    )

    assert plan.state is PlanState.AWAITING_CONFIRMATION
    assert plan.authorization_id is None
    assert plan.plan_fingerprint.startswith("agent-plan:v1:sha256:")
    assert plan.steps[0].arguments["end_state"] == "sale_order"
    assert store.plan == plan


def test_host_normalizes_candidate_step_to_the_executed_preview_trace() -> None:
    proposal_id = UUID("30000000-0000-4000-8000-000000000001")
    fingerprint = "action-payload:v1:sha256:" + "a" * 64
    candidate = _candidate().model_copy(
        update={
            "steps": (
                _candidate().steps[0].model_copy(
                    update={
                        "tool_name": "sale.order.build_flow.v1",
                        "arguments": {"end_state": "sale_order"},
                    }
                ),
            )
        }
    )
    trace = ActionProposalTrace(
        tool_name="odoo.preview_sale_order_build_flow",
        arguments={
            "create_synthetic_partner": True,
            "create_synthetic_product": True,
            "end_state": "sale_order",
            "partner_name": "AI TEST Customer",
            "product_name": "AI TEST Product",
        },
        proposal_id=proposal_id,
        payload_fingerprint=fingerprint,
    )
    proposal = BusinessActionProposalHandle.model_construct(
        proposal_id=proposal_id,
        turn_id=_request(_policy_layers()).turn_id,
        payload_fingerprint=fingerprint,
    )
    report = ActionToolReport.model_construct(
        proposals=(proposal,),
        proposal_traces=(trace,),
    )

    normalized, bindings = _reconcile_previews(
        candidate,
        report,
        turn_id=_request(_policy_layers()).turn_id,
    )

    assert normalized.steps[0].tool_name == trace.tool_name
    assert normalized.steps[0].arguments == trace.arguments
    assert bindings["sale_flow"].proposal_id == proposal_id


def test_approve_creates_opaque_host_authorization_for_the_whole_plan() -> None:
    store = MemoryPlanStore()
    ids = iter((PLAN_ID, AUTH_ID))
    service = AgentPlanService(store, clock=lambda: NOW, id_factory=lambda: next(ids))
    layers = _policy_layers()
    service.create(
        request=_request(layers),
        candidate=_candidate(),
        evaluated=_evaluated(layers),
    )

    result = service.decide(
        AgentPlanDecisionRequest(
            plan_id=PLAN_ID,
            decision="approve",
            actor=ChatActor(database="odoo", uid=7),
        )
    )

    assert result.state is PlanState.AUTHORIZED
    assert result.authorization_id == AUTH_ID
    assert store.plan is not None
    assert store.plan.authorization_source is AuthorizationSource.USER_CONFIRMATION
