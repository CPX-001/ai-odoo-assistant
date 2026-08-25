import asyncio
import json
import threading
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient, Response
from odoo_ai.adapters import OdooGatewayError, OdooGatewayFactory, OdooGatewaySettings
from odoo_ai.api import create_app
from odoo_ai.application import TraceEventData
from odoo_ai.contracts import (
    Evidence,
    EvidenceKind,
    EvidenceSensitivity,
    EvidenceStatus,
    InstanceProfileSummary,
    RecordRef,
    RecordSnapshot,
)
from odoo_ai.security import SHARED_SECRET_HEADER

TURN_ID = UUID("12345678-1234-5678-1234-567812345678")
MACHINE_SECRET = "context-read-secret-" + "s" * 48
DELEGATION_TOKEN = "v1." + "d" * 96


class FakeGateway:
    def __init__(self, *, failure: str | None = None, leaked_value: str | None = None) -> None:
        self.failure = failure
        self.leaked_value = leaked_value
        self.metadata_models: list[str] = []
        self.read_calls: list[tuple[list[RecordRef], list[str]]] = []

    async def get_model_metadata(self, model: str) -> Evidence:
        self.metadata_models.append(model)
        if self.failure:
            raise OdooGatewayError(self.failure)
        return Evidence(
            evidence_id="11111111-1111-4111-8111-111111111111",
            kind=EvidenceKind.METADATA,
            status=EvidenceStatus.CHECKED,
            title="Metadata",
            summary="Effective metadata",
            payload={
                "model": model,
                "fields": {
                    "company_id": {"type": "many2one"},
                    "write_date": {"type": "datetime"},
                    "state": {"type": "selection"},
                    "name": {"type": "char"},
                    "display_name": {"type": "char"},
                },
            },
            observed_at=datetime.now(UTC),
            sensitivity=EvidenceSensitivity.TECHNICAL,
        )

    async def read_records(
        self, records: list[RecordRef], fields: list[str]
    ) -> list[RecordSnapshot]:
        self.read_calls.append((records, fields))
        values: dict[str, Any] = {
            "display_name": "S00042",
            "name": "S00042",
            "state": "sale",
            "company_id": [3, "My Company"],
        }
        if self.leaked_value:
            values["name"] = self.leaked_value
        return [
            RecordSnapshot(
                record=RecordRef(
                    model=records[0].model,
                    id=records[0].id,
                    display_name="S00042",
                ),
                fields={name: values[name] for name in fields},
                captured_at=datetime.now(UTC),
                provenance={"provider": "fake"},
            )
        ]


class FakeGatewayFactory:
    def __init__(self, gateway: FakeGateway) -> None:
        self.gateway = gateway
        self.turn_ids: list[UUID] = []
        self.tokens: list[str] = []

    def for_turn(self, *, turn_id: UUID, delegation_token: object) -> FakeGateway:
        self.turn_ids.append(turn_id)
        self.tokens.append(delegation_token.get_secret_value())
        return self.gateway


@pytest.fixture(autouse=True)
def configured_secret(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    secret_file = tmp_path / "shared-secret"
    secret_file.write_text(MACHINE_SECRET, encoding="utf-8")
    secret_file.chmod(0o640)
    monkeypatch.setenv("ODOO_AI_SHARED_SECRET_FILE", str(secret_file))


def _payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "turn_id": str(TURN_ID),
        "message": "¿Qué estado tiene este pedido?",
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
            "allowed_company_ids": [3, 5],
            "lang": "es_ES",
        },
        "delegation_token": DELEGATION_TOKEN,
        "gateway": {"database": "customer-db"},
    }
    payload.update(overrides)
    return payload


async def _post(app: object, payload: dict[str, object], secret: str | None = MACHINE_SECRET) -> Response:
    transport = ASGITransport(app=app)
    headers = {SHARED_SECRET_HEADER: secret} if secret is not None else {}
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        return await client.post(
            "/v1/turns/context-read", json=payload, headers=headers
        )


def test_valid_turn_rereads_one_record_with_bounded_deterministic_fields() -> None:
    gateway = FakeGateway()
    factory = FakeGatewayFactory(gateway)
    traces: list[tuple[UUID, tuple[TraceEventData, ...]]] = []
    app = create_app(
        gateway_factory=factory,
        instance_loader=lambda: InstanceProfileSummary(instance_id="unknown"),
        trace_writer=lambda trace_id, events: traces.append((trace_id, events)),
    )

    response = asyncio.run(_post(app, _payload()))
    body = response.json()

    assert response.status_code == 200
    assert body["status"] == "ok"
    assert body["turn_id"] == str(TURN_ID)
    assert body["instance_state"] == "unknown"
    assert body["instance_id"] is None
    assert body["fields_read"] == ["display_name", "name", "state", "company_id"]
    assert body["record"]["record"] == {
        "model": "sale.order",
        "id": 42,
        "display_name": "S00042",
    }
    assert body["record"]["fields"]["state"] == "sale"
    assert gateway.metadata_models == ["sale.order"]
    assert gateway.read_calls[0][0] == [RecordRef(model="sale.order", id=42)]
    assert gateway.read_calls[0][1] == [
        "display_name",
        "name",
        "state",
        "company_id",
    ]
    assert factory.turn_ids == [TURN_ID]
    assert factory.tokens == [DELEGATION_TOKEN]
    serialized_traces = repr(traces)
    assert DELEGATION_TOKEN not in response.text
    assert DELEGATION_TOKEN not in serialized_traces
    assert "¿Qué estado" not in serialized_traces


def test_machine_auth_missing_or_invalid_is_rejected() -> None:
    app = create_app(gateway_factory=FakeGatewayFactory(FakeGateway()))

    missing = asyncio.run(_post(app, _payload(), secret=None))
    invalid = asyncio.run(_post(app, _payload(), secret="wrong-secret"))

    assert missing.status_code == 401
    assert invalid.status_code == 401
    assert DELEGATION_TOKEN not in missing.text
    assert MACHINE_SECRET not in invalid.text


def test_oversized_request_is_rejected_before_gateway_use() -> None:
    factory = FakeGatewayFactory(FakeGateway())
    payload = _payload()
    payload["message"] = "x" * (17 * 1024)
    app = create_app(gateway_factory=factory)

    response = asyncio.run(_post(app, payload))

    assert response.status_code == 413
    assert response.json() == {
        "error": {"code": "request_too_large"},
        "ok": False,
    }
    assert factory.turn_ids == []
    assert DELEGATION_TOKEN not in response.text


def test_missing_record_context_is_structured_and_does_not_echo_input() -> None:
    payload = _payload()
    payload["screen"] = {
        "captured_at": datetime.now(UTC).isoformat(),
        "model": None,
        "res_id": None,
    }
    app = create_app(gateway_factory=FakeGatewayFactory(FakeGateway()))

    response = asyncio.run(_post(app, payload))

    assert response.status_code == 422
    assert response.json() == {
        "error": {"code": "record_context_required"},
        "ok": False,
    }
    assert DELEGATION_TOKEN not in response.text


def test_access_denied_is_sanitized_without_record_existence_leak() -> None:
    app = create_app(
        gateway_factory=FakeGatewayFactory(FakeGateway(failure="access_denied"))
    )

    response = asyncio.run(_post(app, _payload()))

    assert response.status_code == 403
    assert response.json() == {"error": {"code": "access_denied"}, "ok": False}
    assert "sale.order" not in response.text
    assert "42" not in response.text


def test_delegation_token_cannot_be_reflected_by_gateway_data() -> None:
    app = create_app(
        gateway_factory=FakeGatewayFactory(
            FakeGateway(leaked_value=DELEGATION_TOKEN)
        )
    )

    response = asyncio.run(_post(app, _payload()))

    assert response.status_code == 502
    assert response.json() == {
        "error": {"code": "unsafe_gateway_response"},
        "ok": False,
    }
    assert DELEGATION_TOKEN not in response.text


class AdapterHandler(BaseHTTPRequestHandler):
    machine_secret = MACHINE_SECRET
    delegation_token = DELEGATION_TOKEN

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        request_payload = json.loads(self.rfile.read(length))
        assert self.headers[SHARED_SECRET_HEADER] == self.machine_secret
        assert self.headers["X-Odoo-AI-Delegation"] == self.delegation_token
        if self.path.endswith("model-metadata"):
            response_payload = {
                "captured_at": datetime.now(UTC).isoformat(),
                "fields": {
                    "display_name": {"type": "char"},
                    "name": {"type": "char"},
                    "state": {"type": "selection"},
                },
                "model": request_payload["model"],
                "ok": True,
            }
        else:
            response_payload = {
                "captured_at": datetime.now(UTC).isoformat(),
                "model": request_payload["model"],
                "ok": True,
                "records": [
                    {
                        "display_name": "S00042",
                        "fields": {
                            name: {"display_name": "S00042", "name": "S00042", "state": "sale"}[name]
                            for name in request_payload["fields"]
                        },
                        "id": request_payload["ids"][0],
                    }
                ],
            }
        body = json.dumps(response_payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        del format, args


def test_context_read_integrates_with_m2_http_gateway_adapter() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 0), AdapterHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        factory = OdooGatewayFactory(
            OdooGatewaySettings(f"http://127.0.0.1:{server.server_port}"),
            secret_loader=lambda: MACHINE_SECRET,
        )
        app = create_app(gateway_factory=factory)

        response = asyncio.run(_post(app, _payload()))

        assert response.status_code == 200
        assert response.json()["record"]["fields"] == {
            "display_name": "S00042",
            "name": "S00042",
            "state": "sale",
        }
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
