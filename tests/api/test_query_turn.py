import asyncio
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient, Response
from odoo_ai.api import create_app
from odoo_ai.application import QueryTurnError
from odoo_ai.contracts import (
    AnswerConfidence,
    QueryCitation,
    QueryTurnRequest,
    QueryTurnResponse,
)
from odoo_ai.security import SHARED_SECRET_HEADER

TURN_ID = UUID("62345678-1234-5678-1234-567812345678")
MACHINE_SECRET = "query-secret-" + "s" * 48
TOKEN = "q1." + "d" * 256


class StubQueryService:
    def __init__(self, failure: QueryTurnError | None = None) -> None:
        self.failure = failure
        self.requests: list[QueryTurnRequest] = []

    async def run(self, request: QueryTurnRequest) -> QueryTurnResponse:
        self.requests.append(request)
        if self.failure:
            raise self.failure
        return QueryTurnResponse(
            turn_id=request.turn_id,
            answer_markdown="Hay dos pedidos.",
            confidence=AnswerConfidence.HIGH,
            citations=(
                QueryCitation(
                    evidence_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
                    model="sale.order",
                    operation="query_records",
                    captured_at=datetime.now(UTC),
                    returned_count=2,
                    limit=20,
                    truncated=False,
                    empty=False,
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
        "message": "¿Cuántos pedidos hay?",
        "screen": {
            "view_type": "list",
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


async def _post(
    app: object, payload: dict[str, object], *, auth: bool = True
) -> Response:
    transport = ASGITransport(app=app)
    headers = {SHARED_SECRET_HEADER: MACHINE_SECRET} if auth else {}
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        return await client.post("/v1/turns/query", json=payload, headers=headers)


def test_query_endpoint_is_machine_authenticated_and_sanitized() -> None:
    service = StubQueryService()
    app = create_app(query_service=service)

    response = asyncio.run(_post(app, _payload()))

    assert response.status_code == 200
    assert response.json()["workflow"] == "QUERY"
    assert response.json()["citations"][0]["operation"] == "query_records"
    assert TOKEN not in response.text
    assert service.requests[0].delegation_token.get_secret_value() == TOKEN
    assert asyncio.run(_post(app, _payload(), auth=False)).status_code == 401


def test_query_validation_and_failures_are_controlled() -> None:
    service = StubQueryService()
    app = create_app(query_service=service)
    invalid = _payload()
    invalid["screen"] = {"model": 3, "captured_at": datetime.now(UTC).isoformat()}

    response = asyncio.run(_post(app, invalid))

    assert response.status_code == 422
    assert response.json() == {"error": {"code": "invalid_request"}, "ok": False}
    assert service.requests == []

    failing = create_app(
        query_service=StubQueryService(QueryTurnError("query_budget_exceeded", 502))
    )
    failure = asyncio.run(_post(failing, _payload()))
    assert failure.status_code == 502
    assert failure.json() == {
        "error": {"code": "query_budget_exceeded"},
        "ok": False,
    }
