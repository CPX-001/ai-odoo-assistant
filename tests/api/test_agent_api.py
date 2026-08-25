import asyncio
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from odoo_ai.api import create_app
from odoo_ai.application.agent_turn import AgentTurnError
from odoo_ai.contracts import (
    AgentPlanDecisionRequest,
    AgentPlanDecisionResponse,
    AgentTurnRequest,
    AgentTurnResponse,
    AnswerConfidence,
    PlanState,
)
from odoo_ai.runtime.agent_failure_diagnosis import AgentFailureDiagnosis
from odoo_ai.security import SHARED_SECRET_HEADER

SECRET = "agent-api-secret-" + "s" * 48
PLAN_ID = UUID("10000000-0000-4000-8000-000000000001")
AUTHORIZATION_ID = UUID("10000000-0000-4000-8000-000000000002")


class StubTurnService:
    def __init__(self) -> None:
        self.requests: list[AgentTurnRequest] = []

    async def run(self, request: AgentTurnRequest) -> AgentTurnResponse:
        self.requests.append(request)
        return AgentTurnResponse(
            turn_id=request.turn_id,
            conversation_id=request.conversation_id,
            state=PlanState.COMPLETED,
            answer_markdown="Respuesta verificada por el host.",
            confidence=AnswerConfidence.HIGH,
            completed_at=datetime.now(UTC),
        )


class FailingTurnService:
    def __init__(self, code: str) -> None:
        self.code = code

    async def run(self, request: AgentTurnRequest) -> AgentTurnResponse:
        del request
        raise AgentTurnError(self.code, 503)


class StubPlanService:
    def __init__(self) -> None:
        self.decisions: list[AgentPlanDecisionRequest] = []

    def decide(self, request: AgentPlanDecisionRequest) -> AgentPlanDecisionResponse:
        self.decisions.append(request)
        return AgentPlanDecisionResponse(
            plan_id=request.plan_id,
            state=PlanState.AUTHORIZED,
            authorization_id=AUTHORIZATION_ID,
            decided_at=datetime.now(UTC),
        )


class StubAgentFactory:
    def __init__(
        self,
        turn: object | None = None,
        diagnosis: AgentFailureDiagnosis | None = None,
    ) -> None:
        self.turn = turn or StubTurnService()
        self.plans = StubPlanService()
        self.diagnosis = diagnosis
        self.diagnose_calls: list[tuple[UUID, str]] = []

    def turn_service(self, request: AgentTurnRequest) -> object:
        del request
        return self.turn

    def plan_service(self) -> StubPlanService:
        return self.plans

    def execution_service(self) -> object:
        return object()

    async def diagnose_failure(
        self,
        request: AgentTurnRequest,
        code: str,
    ) -> AgentFailureDiagnosis | None:
        self.diagnose_calls.append((request.turn_id, code))
        return self.diagnosis


@pytest.fixture(autouse=True)
def configured_secret(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    secret_file = tmp_path / "shared-secret"
    secret_file.write_text(SECRET, encoding="utf-8")
    secret_file.chmod(0o640)
    monkeypatch.setenv("ODOO_AI_SHARED_SECRET_FILE", str(secret_file))


def _turn_payload() -> dict[str, object]:
    permissive = {
        "confirmation_mode": "protected_only",
        "max_auto_risk": "high",
        "allow_synthetic_data": True,
        "max_tool_calls_per_turn": 32,
        "max_write_steps_per_plan": 12,
        "max_replans": 2,
        "max_consecutive_failures": 3,
    }
    return {
        "turn_id": str(uuid4()),
        "actor": {"database": "customer-db", "uid": 17},
        "conversation_id": None,
        "message": "Consulta el modelo OCA instalado",
        "screen": {
            "action_id": None,
            "menu_id": None,
            "view_type": None,
            "model": None,
            "res_id": None,
            "selected_ids": [],
            "allowed_context_subset": {},
            "captured_at": datetime.now(UTC).isoformat(),
        },
        "user": {
            "uid": 17,
            "company_id": 3,
            "allowed_company_ids": [3],
            "lang": "es_ES",
        },
        "gateway": {"database": "customer-db"},
        "capability_token": "opaque-ag1-token",
        "candidates": [{"model": "sale.order", "labels": ["Pedidos"]}],
        "policy_layers": {
            "system_ceiling": permissive,
            "administrator": permissive,
            "user": {**permissive, "max_auto_risk": "low"},
            "conversation": permissive,
        },
        "synthetic_data_authorized": False,
    }


async def _post(app: object, path: str, payload: object, *, auth: bool = True):
    headers = {SHARED_SECRET_HEADER: SECRET} if auth else {}
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        return await client.post(path, json=payload, headers=headers)


def test_agent_turn_requires_machine_auth_and_never_accepts_authority_fields() -> None:
    factory = StubAgentFactory()
    app = create_app(agent_service_factory=factory)  # type: ignore[arg-type]
    payload = _turn_payload()

    unauthenticated = asyncio.run(_post(app, "/v1/agent/turn", payload, auth=False))
    valid = asyncio.run(_post(app, "/v1/agent/turn", payload))
    injected = asyncio.run(
        _post(app, "/v1/agent/turn", {**payload, "authorization_id": str(uuid4())})
    )

    assert unauthenticated.status_code == 401
    assert valid.status_code == 200
    assert valid.json()["state"] == "completed"
    assert "capability_token" not in valid.text
    assert injected.status_code == 422
    assert isinstance(factory.turn, StubTurnService)
    assert len(factory.turn.requests) == 1


@pytest.mark.parametrize(
    ("code", "expected_fragment"),
    [
        ("access_denied", "permisos"),
        ("agent_engine_timeout", "sin tiempo"),
        ("tool_call_budget_exceeded", "demasiadas comprobaciones"),
    ],
)
def test_agent_turn_has_a_plain_fallback_when_diagnosis_is_unavailable(
    code: str,
    expected_fragment: str,
) -> None:
    factory = StubAgentFactory(FailingTurnService(code))
    app = create_app(agent_service_factory=factory)  # type: ignore[arg-type]

    response = asyncio.run(_post(app, "/v1/agent/turn", _turn_payload()))

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["state"] == "failed"
    assert payload["confidence"] == "low"
    assert payload["plan"]["state"] == "failed"
    assert payload["plan"]["steps"] == []
    assert payload["plan"]["requires_confirmation"] is False
    assert expected_fragment in payload["answer_markdown"]
    assert "**Diagnóstico.**" not in payload["answer_markdown"]
    assert "App Server" not in payload["answer_markdown"]
    assert "ACL" not in payload["answer_markdown"]
    assert code not in response.text
    assert len(factory.diagnose_calls) == 1


def test_agent_turn_prefers_evidence_backed_model_diagnosis() -> None:
    diagnosis = AgentFailureDiagnosis(
        answer_markdown=(
            "He podido comprobar que el intento se interrumpió mientras el servicio interno "
            "estaba degradado. No se aplicó ningún cambio. Puedo volver a intentarlo si quieres."
        ),
        confidence=AnswerConfidence.MEDIUM,
    )
    factory = StubAgentFactory(
        FailingTurnService("tool_call_budget_exceeded"),
        diagnosis=diagnosis,
    )
    app = create_app(agent_service_factory=factory)  # type: ignore[arg-type]

    response = asyncio.run(_post(app, "/v1/agent/turn", _turn_payload()))

    assert response.status_code == 200
    payload = response.json()
    assert payload["answer_markdown"] == diagnosis.answer_markdown
    assert payload["confidence"] == "medium"
    assert payload["plan"]["state"] == "failed"
    assert payload["plan"]["steps"] == []
    assert "tool_call_budget_exceeded" not in response.text
    assert len(factory.diagnose_calls) == 1


def test_grouped_decision_is_bound_to_path_plan_and_authenticated_actor() -> None:
    factory = StubAgentFactory()
    app = create_app(agent_service_factory=factory)  # type: ignore[arg-type]
    payload = {
        "plan_id": str(PLAN_ID),
        "decision": "approve",
        "actor": {"database": "customer-db", "uid": 17},
    }

    valid = asyncio.run(
        _post(app, f"/v1/agent/plans/{PLAN_ID}/decision", payload)
    )
    mismatch = asyncio.run(
        _post(app, f"/v1/agent/plans/{uuid4()}/decision", payload)
    )

    assert valid.status_code == 200
    assert valid.json()["authorization_id"] == str(AUTHORIZATION_ID)
    assert mismatch.status_code == 422
    assert factory.plans.decisions == [AgentPlanDecisionRequest(**payload)]
