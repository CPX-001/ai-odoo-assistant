import asyncio
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient, Response
from odoo_ai.api import create_app
from odoo_ai.application import ExplainTurnError
from odoo_ai.contracts import (
    AnswerConfidence,
    ExplainTurnRequest,
    ExplainTurnResponse,
    RecordCitation,
)
from odoo_ai.security import SHARED_SECRET_HEADER

TURN_ID = UUID("12345678-1234-5678-1234-567812345678")
MACHINE_SECRET = "explain-secret-" + "s" * 48
DELEGATION_TOKEN = "v1." + "d" * 96


class StubExplainService:
    def __init__(self, failure: ExplainTurnError | None = None) -> None:
        self.failure = failure
        self.requests: list[ExplainTurnRequest] = []

    async def run(self, request: ExplainTurnRequest) -> ExplainTurnResponse:
        self.requests.append(request)
        if self.failure:
            raise self.failure
        return ExplainTurnResponse(
            turn_id=request.turn_id,
            answer_markdown="El registro y el source explican la tarea.",
            confidence=AnswerConfidence.HIGH,
            citations=(
                RecordCitation(
                    evidence_id="11111111-1111-4111-8111-111111111111",
                    model="sale.order",
                    id=42,
                    display_name="S00042",
                    captured_at=datetime.now(UTC),
                ),
            ),
            completed_at=datetime.now(UTC),
        )


@pytest.fixture(autouse=True)
def configured_secret(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    secret_file = tmp_path / "shared-secret"
    secret_file.write_text(MACHINE_SECRET, encoding="utf-8")
    secret_file.chmod(0o640)
    monkeypatch.setenv("ODOO_AI_SHARED_SECRET_FILE", str(secret_file))


def _payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "turn_id": str(TURN_ID),
        "message": "¿Por qué confirmar este pedido crea una tarea?",
        "screen": {
            "action_id": 42,
            "menu_id": 7,
            "view_type": "form",
            "model": "sale.order",
            "res_id": 42,
            "selected_ids": [42],
            "allowed_context_subset": {
                "active_id": 42,
                "active_model": "sale.order",
            },
            "captured_at": datetime.now(UTC).isoformat(),
        },
        "user": {
            "uid": 17,
            "company_id": 3,
            "allowed_company_ids": [3],
            "lang": "es_ES",
        },
        "delegation_token": DELEGATION_TOKEN,
        "gateway": {"database": "customer-db"},
    }
    payload.update(overrides)
    return payload


async def _post(
    app: object,
    payload: dict[str, object],
    secret: str | None = MACHINE_SECRET,
) -> Response:
    transport = ASGITransport(app=app)
    headers = {SHARED_SECRET_HEADER: secret} if secret is not None else {}
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        return await client.post("/v1/turns/explain", json=payload, headers=headers)


def test_explain_endpoint_has_machine_auth_and_explicit_response_model() -> None:
    service = StubExplainService()
    app = create_app(explain_service=service)

    response = asyncio.run(_post(app, _payload()))

    assert response.status_code == 200
    assert response.json() == {
        "turn_id": str(TURN_ID),
        "status": "ok",
        "answer_markdown": "El registro y el source explican la tarea.",
        "workflow": "EXPLAIN",
        "confidence": "high",
        "limitations": [],
        "citations": [
            {
                "kind": "record",
                "evidence_id": "11111111-1111-4111-8111-111111111111",
                "model": "sale.order",
                "id": 42,
                "display_name": "S00042",
                "captured_at": response.json()["citations"][0]["captured_at"],
            }
        ],
        "completed_at": response.json()["completed_at"],
    }
    assert service.requests[0].delegation_token.get_secret_value() == DELEGATION_TOKEN
    assert DELEGATION_TOKEN not in response.text

    missing_auth = asyncio.run(_post(app, _payload(), secret=None))
    assert missing_auth.status_code == 401


def test_invalid_and_oversized_requests_are_controlled_before_workflow() -> None:
    service = StubExplainService()
    app = create_app(explain_service=service)
    invalid = _payload()
    invalid["screen"] = {
        "captured_at": datetime.now(UTC).isoformat(),
        "model": 3,
    }
    oversized = _payload(message="x" * (17 * 1024))

    invalid_response = asyncio.run(_post(app, invalid))
    oversized_response = asyncio.run(_post(app, oversized))

    assert invalid_response.status_code == 422
    assert invalid_response.json() == {
        "error": {"code": "invalid_request"},
        "ok": False,
    }
    assert oversized_response.status_code == 413
    assert oversized_response.json() == {
        "error": {"code": "request_too_large"},
        "ok": False,
    }
    assert service.requests == []


@pytest.mark.parametrize(
    ("code", "status_code"),
    [
        ("access_denied", 403),
        ("engine_unavailable", 503),
        ("evidence_unavailable", 503),
        ("engine_timeout", 504),
    ],
)
def test_explain_failures_are_sanitized(code: str, status_code: int) -> None:
    service = StubExplainService(ExplainTurnError(code, status_code))
    app = create_app(explain_service=service)

    response = asyncio.run(_post(app, _payload()))

    assert response.status_code == status_code
    assert response.json() == {"error": {"code": code}, "ok": False}
    assert DELEGATION_TOKEN not in response.text


def test_unexpected_engine_failure_is_reduced_without_details() -> None:
    class BrokenService:
        async def run(self, request: ExplainTurnRequest) -> ExplainTurnResponse:
            del request
            raise RuntimeError("provider-secret-detail")

    response = asyncio.run(_post(create_app(explain_service=BrokenService()), _payload()))

    assert response.status_code == 503
    assert response.json() == {
        "error": {"code": "engine_unavailable"},
        "ok": False,
    }
    assert "provider-secret-detail" not in response.text
