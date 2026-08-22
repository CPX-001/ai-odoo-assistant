import asyncio
import json
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest

from odoo_ai.adapters import (
    HttpOdooGateway,
    HttpOdooInstanceGateway,
    OdooGatewayError,
    OdooGatewayFactory,
    OdooGatewaySettings,
)
from odoo_ai.adapters.odoo_http import (
    DELEGATION_HEADER,
    INVENTORY_ROUTE,
    MAX_RESPONSE_BYTES,
    METADATA_ROUTE,
    NAVIGATION_ROUTE,
    ODOO_BASE_URL_ENV,
    READ_ROUTE,
)
from odoo_ai.contracts import EvidenceKind, EvidenceStatus, RecordRef
from odoo_ai.security import SHARED_SECRET_HEADER

TURN_ID = UUID("12345678-1234-5678-1234-567812345678")
MACHINE_SECRET = "machine-" + "m" * 48
DELEGATION_TOKEN = "v1." + "d" * 96


@dataclass(slots=True)
class ResponseSpec:
    status: int = 200
    body: bytes = b"{}"
    content_type: str = "application/json"
    delay_seconds: float = 0
    headers: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class CapturedRequest:
    path: str
    headers: dict[str, str]
    body: bytes


Responder = Callable[[CapturedRequest], ResponseSpec]


class FakeOdooServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, responder: Responder) -> None:
        super().__init__(("127.0.0.1", 0), FakeOdooHandler)
        self.responder = responder
        self.requests: list[CapturedRequest] = []


class FakeOdooHandler(BaseHTTPRequestHandler):
    server: FakeOdooServer

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        captured = CapturedRequest(
            path=self.path,
            headers={key: value for key, value in self.headers.items()},
            body=self.rfile.read(length),
        )
        self.server.requests.append(captured)
        spec = self.server.responder(captured)
        if spec.delay_seconds:
            time.sleep(spec.delay_seconds)
        self.send_response(spec.status)
        self.send_header("Content-Type", spec.content_type)
        self.send_header("Content-Length", str(len(spec.body)))
        for name, value in spec.headers.items():
            self.send_header(name, value)
        self.end_headers()
        try:
            self.wfile.write(spec.body)
        except BrokenPipeError:
            pass

    def log_message(self, format: str, *args: Any) -> None:
        del format, args


@contextmanager
def fake_odoo_server(responder: Responder) -> Iterator[FakeOdooServer]:
    server = FakeOdooServer(responder)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def _json_response(payload: dict[str, object]) -> ResponseSpec:
    return ResponseSpec(body=json.dumps(payload).encode("utf-8"))


def _factory(base_url: str, **settings: object) -> OdooGatewayFactory:
    return OdooGatewayFactory(
        OdooGatewaySettings(base_url=base_url, **settings),
        secret_loader=lambda: MACHINE_SECRET,
    )


def _gateway(base_url: str, **settings: object) -> HttpOdooGateway:
    return _factory(base_url, **settings).for_turn(
        turn_id=TURN_ID,
        delegation_token=DELEGATION_TOKEN,
    )


def test_nondefault_url_metadata_maps_to_checked_evidence() -> None:
    def responder(request: CapturedRequest) -> ResponseSpec:
        assert request.path == METADATA_ROUTE
        return _json_response(
            {
                "captured_at": "2026-08-21T10:30:00Z",
                "fields": {
                    "name": {
                        "readonly": False,
                        "required": True,
                        "string": "Name",
                        "type": "char",
                    }
                },
                "model": "sale.order",
                "ok": True,
            }
        )

    with fake_odoo_server(responder) as server:
        base_url = f"http://127.0.0.1:{server.server_port}"
        evidence = asyncio.run(_gateway(base_url).get_model_metadata("sale.order"))

    assert evidence.kind is EvidenceKind.METADATA
    assert evidence.status is EvidenceStatus.CHECKED
    assert evidence.payload["model"] == "sale.order"
    assert evidence.payload["fields"] == {
        "name": {
            "readonly": False,
            "required": True,
            "string": "Name",
            "type": "char",
        }
    }


def test_metadata_rejects_duplicate_json_keys() -> None:
    def responder(request: CapturedRequest) -> ResponseSpec:
        assert request.path == METADATA_ROUTE
        return ResponseSpec(
            status=200,
            headers={"Content-Type": "application/json"},
            body=(
                b'{"captured_at":"2026-08-21T10:30:00Z","fields":'
                b'{"name":{"type":"char"},"name":{"type":"text"}},'
                b'"model":"sale.order","ok":true}'
            ),
        )

    with fake_odoo_server(responder) as server:
        base_url = f"http://127.0.0.1:{server.server_port}"
        with pytest.raises(OdooGatewayError, match="malformed_response"):
            asyncio.run(_gateway(base_url).get_model_metadata("sale.order"))


def test_machine_only_instance_inventory_is_bounded_and_validated() -> None:
    def responder(request: CapturedRequest) -> ResponseSpec:
        assert request.path == INVENTORY_ROUTE
        assert DELEGATION_HEADER not in request.headers
        assert request.headers[SHARED_SECRET_HEADER] == MACHINE_SECRET
        return _json_response(
            {
                "addons_roots": ["/srv/customer/addons"],
                "captured_at": "2026-08-22T10:30:00Z",
                "database": "customer_odoo",
                "installed_modules": ["base", "sale"],
                "ok": True,
                "server_version": "18.0",
            }
        )

    with fake_odoo_server(responder) as server:
        gateway = _factory(f"http://127.0.0.1:{server.server_port}").for_instance()
        inventory = asyncio.run(gateway.get_instance_inventory())

    assert inventory.database == "customer_odoo"
    assert inventory.installed_modules == ("base", "sale")
    assert inventory.addons_roots == ("/srv/customer/addons",)
    assert MACHINE_SECRET not in repr(gateway)


def test_navigation_maps_only_bounded_visible_metadata() -> None:
    def responder(request: CapturedRequest) -> ResponseSpec:
        assert request.path == NAVIGATION_ROUTE
        assert json.loads(request.body) == {"turn_id": str(TURN_ID)}
        assert request.headers[DELEGATION_HEADER] == DELEGATION_TOKEN
        assert request.headers[SHARED_SECRET_HEADER] == MACHINE_SECRET
        return _json_response(
            {
                "captured_at": "2026-08-22T10:30:00Z",
                "content_trust": "untrusted",
                "limits": {"max_bytes": 131072, "max_depth": 8, "max_nodes": 256},
                "nodes": [
                    {
                        "action": {
                            "action_type": "ir.actions.act_window",
                            "target_model": "sale.order",
                            "view_modes": ["list", "form"],
                        },
                        "label": "Orders",
                        "menu_id": 42,
                        "parent_id": None,
                        "path": ["Orders"],
                        "sequence": 10,
                    }
                ],
                "ok": True,
                "truncated": False,
            }
        )

    with fake_odoo_server(responder) as server:
        base_url = f"http://127.0.0.1:{server.server_port}"
        navigation = asyncio.run(_gateway(base_url).get_navigation())

    assert navigation.nodes[0].menu_id == 42
    assert navigation.nodes[0].action is not None
    assert navigation.nodes[0].action.target_model == "sale.order"
    assert navigation.content_trust == "untrusted"


def test_valid_read_maps_exact_records_and_sends_both_server_credentials() -> None:
    def responder(request: CapturedRequest) -> ResponseSpec:
        assert request.path == READ_ROUTE
        return _json_response(
            {
                "captured_at": "2026-08-21T10:31:00Z",
                "model": "sale.order",
                "ok": True,
                "records": [
                    {
                        "display_name": "S00042",
                        "fields": {"name": "S00042", "state": "sale"},
                        "id": 42,
                    }
                ],
            }
        )

    with fake_odoo_server(responder) as server:
        gateway = _gateway(f"http://127.0.0.1:{server.server_port}")
        snapshots = asyncio.run(
            gateway.read_records(
                [RecordRef(model="sale.order", id=42)],
                ["name", "state"],
            )
        )
        captured = server.requests[0]

    assert snapshots[0].record.display_name == "S00042"
    assert snapshots[0].fields == {"name": "S00042", "state": "sale"}
    assert captured.headers[SHARED_SECRET_HEADER] == MACHINE_SECRET
    assert captured.headers[DELEGATION_HEADER] == DELEGATION_TOKEN
    assert json.loads(captured.body) == {
        "fields": ["name", "state"],
        "ids": [42],
        "model": "sale.order",
        "turn_id": str(TURN_ID),
    }
    assert MACHINE_SECRET not in repr(gateway)
    assert DELEGATION_TOKEN not in repr(gateway)


def test_factory_reuses_the_m1_secret_file_loader(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    secret_file = tmp_path / "shared-secret"
    secret_file.write_text(MACHINE_SECRET, encoding="utf-8")
    secret_file.chmod(0o640)
    monkeypatch.setenv("ODOO_AI_SHARED_SECRET_FILE", str(secret_file))

    gateway = OdooGatewayFactory(OdooGatewaySettings("http://localhost:8069")).for_turn(
        turn_id=TURN_ID,
        delegation_token=DELEGATION_TOKEN,
    )

    assert MACHINE_SECRET not in repr(gateway)
    assert DELEGATION_TOKEN not in repr(gateway)


@pytest.mark.parametrize(
    "url",
    [
        "",
        "localhost:8069",
        "ftp://localhost:8069",
        "http://user:password@localhost:8069",
        "http://localhost:8069/base",
        "http://localhost:8069?db=customer",
        "http://localhost:8069#fragment",
        "http://localhost:99999",
    ],
)
def test_invalid_or_credential_bearing_urls_are_rejected(url: str) -> None:
    with pytest.raises(OdooGatewayError, match="invalid_gateway_url"):
        OdooGatewaySettings(url)


def test_settings_require_server_side_env_and_accept_nondefault_port() -> None:
    with pytest.raises(OdooGatewayError, match="gateway_unconfigured"):
        OdooGatewaySettings.from_env({})

    settings = OdooGatewaySettings.from_env(
        {ODOO_BASE_URL_ENV: "http://odoo.internal:18069"}
    )

    assert settings.base_url == "http://odoo.internal:18069"


def test_redirect_is_rejected_without_following_location() -> None:
    def responder(request: CapturedRequest) -> ResponseSpec:
        del request
        return ResponseSpec(
            status=307,
            headers={"Location": "http://attacker.invalid/capture"},
        )

    with fake_odoo_server(responder) as server:
        gateway = _gateway(f"http://127.0.0.1:{server.server_port}")
        with pytest.raises(OdooGatewayError, match="redirect_rejected") as failure:
            asyncio.run(gateway.get_model_metadata("sale.order"))

    assert "attacker" not in str(failure.value)
    assert len(server.requests) == 1


def test_timeout_is_sanitized() -> None:
    def responder(request: CapturedRequest) -> ResponseSpec:
        del request
        return ResponseSpec(delay_seconds=0.15)

    with fake_odoo_server(responder) as server:
        gateway = _gateway(
            f"http://127.0.0.1:{server.server_port}", timeout_seconds=0.02
        )
        with pytest.raises(OdooGatewayError, match="upstream_timeout") as failure:
            asyncio.run(gateway.get_model_metadata("sale.order"))

    assert MACHINE_SECRET not in str(failure.value)
    assert DELEGATION_TOKEN not in str(failure.value)


def test_request_body_cap_is_enforced_before_connecting() -> None:
    gateway = _gateway("http://127.0.0.1:9", max_request_bytes=1)

    with pytest.raises(OdooGatewayError, match="request_too_large"):
        asyncio.run(gateway.get_model_metadata("sale.order"))


@pytest.mark.parametrize(
    "response",
    [
        ResponseSpec(body=b"not-json"),
        ResponseSpec(body=b"x" * (MAX_RESPONSE_BYTES + 1)),
        ResponseSpec(body=b"{}", content_type="text/plain"),
    ],
)
def test_oversized_or_malformed_bodies_are_rejected(response: ResponseSpec) -> None:
    with fake_odoo_server(lambda request: response) as server:
        gateway = _gateway(f"http://127.0.0.1:{server.server_port}")
        with pytest.raises(
            OdooGatewayError, match="malformed_response|response_too_large"
        ):
            asyncio.run(gateway.get_model_metadata("sale.order"))


@pytest.mark.parametrize(
    ("status", "code"),
    [
        (401, "machine_auth_rejected"),
        (403, "delegation_rejected"),
        (404, "endpoint_unavailable"),
        (429, "rate_limited"),
        (503, "upstream_unavailable"),
    ],
)
def test_upstream_statuses_map_to_sanitized_errors(status: int, code: str) -> None:
    with fake_odoo_server(lambda request: ResponseSpec(status=status)) as server:
        gateway = _gateway(f"http://127.0.0.1:{server.server_port}")
        with pytest.raises(OdooGatewayError, match=code) as failure:
            asyncio.run(gateway.get_model_metadata("sale.order"))

    assert MACHINE_SECRET not in str(failure.value)
    assert DELEGATION_TOKEN not in str(failure.value)


def test_adapter_exposes_no_generic_odoo_method() -> None:
    assert not hasattr(HttpOdooGateway, "execute_kw")
    assert not hasattr(HttpOdooGateway, "execute_method")
    assert not hasattr(HttpOdooGateway, "search")
    assert not hasattr(HttpOdooInstanceGateway, "execute_method")
