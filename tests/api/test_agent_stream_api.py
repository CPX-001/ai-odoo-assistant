import asyncio
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from odoo_ai.api import create_app
from odoo_ai.api.agent import AgentRequestLimitMiddleware
from odoo_ai.application.agent_events import current_agent_delta_sink
from odoo_ai.application.agent_turn import AgentTurnError
from odoo_ai.contracts import (
    AgentTurnRequest,
    AgentTurnResponse,
    AnswerConfidence,
    PlanState,
)
from odoo_ai.runtime.agent_failure_diagnosis import AgentFailureDiagnosis
from odoo_ai.security import SHARED_SECRET_HEADER

SECRET = "agent-stream-secret-" + "s" * 48


class StreamingStubTurnService:
    async def run(self, request: AgentTurnRequest) -> AgentTurnResponse:
        sink = current_agent_delta_sink()
        assert sink is not None
        for value in ("Hola ", "mundo"):
            emitted = sink(value)
            if asyncio.iscoroutine(emitted):
                await emitted
        return AgentTurnResponse(
            turn_id=request.turn_id,
            conversation_id=request.conversation_id,
            state=PlanState.COMPLETED,
            answer_markdown="Hola mundo",
            confidence=AnswerConfidence.HIGH,
            completed_at=datetime.now(UTC),
        )


class FailingStubTurnService:
    def __init__(self, code: str = "agent_engine_timeout") -> None:
        self.code = code

    async def run(self, request: AgentTurnRequest) -> AgentTurnResponse:
        del request
        raise AgentTurnError(self.code, 504)


class StubFactory:
    def __init__(self, service, diagnosis: AgentFailureDiagnosis | None = None) -> None:
        self.service = service
        self.diagnosis = diagnosis

    def turn_service(self, request):
        del request
        return self.service

    def plan_service(self):
        return object()

    def execution_service(self):
        return object()

    async def diagnose_failure(self, request, code):
        del request, code
        return self.diagnosis


@pytest.fixture(autouse=True)
def configured_secret(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    secret_file = tmp_path / "shared-secret"
    secret_file.write_text(SECRET, encoding="utf-8")
    secret_file.chmod(0o640)
    monkeypatch.setenv("ODOO_AI_SHARED_SECRET_FILE", str(secret_file))


def _payload() -> dict[str, object]:
    layer = {
        "confirmation_mode": "risk_based",
        "max_auto_risk": "low",
        "allow_synthetic_data": False,
        "max_tool_calls_per_turn": 32,
        "max_write_steps_per_plan": 12,
        "max_replans": 2,
        "max_consecutive_failures": 3,
    }
    return {
        "turn_id": str(uuid4()),
        "actor": {"database": "customer-db", "uid": 17},
        "conversation_id": None,
        "message": "Resume los pedidos",
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
        "candidates": [{"model": "sale.order", "labels": []}],
        "policy_layers": {
            "system_ceiling": layer,
            "administrator": layer,
            "user": layer,
            "conversation": layer,
        },
        "synthetic_data_authorized": False,
    }


async def _post_stream(app) -> str:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/v1/agent/turn/stream",
            json=_payload(),
            headers={SHARED_SECRET_HEADER: SECRET},
        )
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        return response.text


def test_stream_emits_only_visible_deltas_then_final_response() -> None:
    app = create_app(
        agent_service_factory=StubFactory(StreamingStubTurnService())  # type: ignore[arg-type]
    )

    stream = asyncio.run(_post_stream(app))

    assert stream.count("event: delta") == 2
    assert '"text":"Hola "' in stream
    assert '"text":"mundo"' in stream
    assert stream.count("event: final") == 1
    assert '"answer_markdown":"Hola mundo"' in stream
    assert "event: error" not in stream
    assert "opaque-ag1-token" not in stream


def test_stream_failure_finishes_with_plain_fallback() -> None:
    app = create_app(
        agent_service_factory=StubFactory(FailingStubTurnService())  # type: ignore[arg-type]
    )

    stream = asyncio.run(_post_stream(app))

    assert "event: delta" not in stream
    assert stream.count("event: final") == 1
    assert "se ha quedado sin tiempo" in stream
    assert "Diagnóstico." not in stream
    assert "App Server" not in stream
    assert "agent_engine_timeout" not in stream
    assert "event: error" not in stream


def test_stream_failure_uses_model_diagnosis_in_final_event() -> None:
    diagnosis = AgentFailureDiagnosis(
        answer_markdown=(
            "He podido comprobar que el intento se interrumpió antes de terminar. "
            "No se aplicó ningún cambio."
        ),
        confidence=AnswerConfidence.MEDIUM,
    )
    app = create_app(
        agent_service_factory=StubFactory(
            FailingStubTurnService("tool_call_budget_exceeded"),
            diagnosis=diagnosis,
        )  # type: ignore[arg-type]
    )

    stream = asyncio.run(_post_stream(app))

    assert stream.count("event: final") == 1
    assert diagnosis.answer_markdown in stream
    assert '"confidence":"medium"' in stream
    assert "tool_call_budget_exceeded" not in stream
    assert "event: error" not in stream


def test_request_limit_replays_body_once_then_forwards_disconnect() -> None:
    received = []

    async def downstream(scope, receive, send) -> None:
        del scope, send
        received.append(await receive())
        received.append(await receive())

    upstream = iter(
        (
            {"type": "http.request", "body": b'{"test":true}', "more_body": False},
            {"type": "http.disconnect"},
        )
    )

    async def receive():
        return next(upstream)

    async def send(message) -> None:
        del message

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/v1/agent/turn/stream",
        "headers": [],
    }
    middleware = AgentRequestLimitMiddleware(downstream, max_bytes=1024)

    asyncio.run(middleware(scope, receive, send))

    assert received == [
        {"type": "http.request", "body": b'{"test":true}', "more_body": False},
        {"type": "http.disconnect"},
    ]
