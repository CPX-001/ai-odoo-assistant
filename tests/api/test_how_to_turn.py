import asyncio
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient, Response
from odoo_ai.api import create_app
from odoo_ai.application import HowToTurnError
from odoo_ai.contracts import (
    AnswerConfidence,
    DocumentCitation,
    HowToTurnRequest,
    HowToTurnResponse,
)
from odoo_ai.security import SHARED_SECRET_HEADER

TURN_ID = UUID("82345678-1234-5678-9234-567812345678")
MACHINE_SECRET = "how-to-secret-" + "s" * 48
TOKEN = "v1." + "d" * 256


class StubHowToService:
    def __init__(self, failure: HowToTurnError | None = None) -> None:
        self.failure = failure
        self.requests: list[HowToTurnRequest] = []

    async def run(self, request: HowToTurnRequest) -> HowToTurnResponse:
        self.requests.append(request)
        if self.failure:
            raise self.failure
        return HowToTurnResponse(
            turn_id=request.turn_id,
            answer_markdown='<script>alert("untrusted")</script> Ve a Ventas.',
            confidence=AnswerConfidence.MEDIUM,
            limitations=("La ruta exacta depende de la instalación.",),
            citations=(
                DocumentCitation(
                    evidence_id="cccccccc-cccc-4ccc-8ccc-cccccccccccc",
                    provider_id="odoo-docs",
                    document_id="sales/orders.md",
                    title="Sales guide",
                    locale="es_ES",
                    media_type="text/markdown",
                    ordinal=0,
                    start_line=10,
                    end_line=12,
                    fingerprint="sha256:" + "d" * 64,
                ),
            ),
            completed_at=datetime.now(UTC),
        )


@pytest.fixture(autouse=True)
def configured_secret(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "shared-secret"
    path.write_text(MACHINE_SECRET, encoding="utf-8")
    path.chmod(0o640)
    monkeypatch.setenv("ODOO_AI_SHARED_SECRET_FILE", str(path))


def _payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "turn_id": str(TURN_ID),
        "message": "¿Cómo confirmo un pedido?",
        "screen": {
            "menu_id": 11,
            "view_type": "form",
            "model": "sale.order",
            "selected_ids": [],
            "captured_at": datetime.now(UTC).isoformat(),
        },
        "user": {
            "uid": 17,
            "company_id": 3,
            "allowed_company_ids": [3],
            "lang": "es_ES",
        },
        "delegation_token": TOKEN,
        "gateway": {"database": "customer-db"},
    }
    payload.update(overrides)
    return payload


async def _post(app: object, payload: dict[str, object], *, auth: bool = True) -> Response:
    headers = {SHARED_SECRET_HEADER: MACHINE_SECRET} if auth else {}
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        return await client.post("/v1/turns/how-to", json=payload, headers=headers)


def test_how_to_endpoint_is_authenticated_bounded_and_keeps_content_as_data() -> None:
    service = StubHowToService()
    app = create_app(how_to_service=service)

    response = asyncio.run(_post(app, _payload()))

    assert response.status_code == 200
    assert response.json()["workflow"] == "HOW_TO"
    assert response.json()["answer_markdown"].startswith("<script>")
    assert TOKEN not in response.text
    assert service.requests[0].delegation_token.get_secret_value() == TOKEN
    assert asyncio.run(_post(app, _payload(), auth=False)).status_code == 401

    too_large = _payload(message="x" * 20_000)
    rejected = asyncio.run(_post(app, too_large))
    assert rejected.status_code == 413
    assert rejected.json() == {"error": {"code": "request_too_large"}, "ok": False}


def test_how_to_validation_and_failures_are_sanitized() -> None:
    service = StubHowToService()
    app = create_app(how_to_service=service)
    invalid = _payload()
    invalid["screen"] = {"model": 3, "captured_at": datetime.now(UTC).isoformat()}

    response = asyncio.run(_post(app, invalid))

    assert response.status_code == 422
    assert response.json() == {"error": {"code": "invalid_request"}, "ok": False}
    assert service.requests == []

    failing = create_app(
        how_to_service=StubHowToService(HowToTurnError("engine_timeout", 504))
    )
    failure = asyncio.run(_post(failing, _payload()))
    assert failure.status_code == 504
    assert failure.json() == {"error": {"code": "engine_timeout"}, "ok": False}
