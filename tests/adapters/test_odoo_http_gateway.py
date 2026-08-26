import asyncio
import json
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest

from odoo_ai.adapters import (
    HttpOdooInstanceGateway,
    OdooGatewayError,
    OdooGatewayFactory,
    OdooGatewaySettings,
)
from odoo_ai.adapters.odoo_http import (
    INVENTORY_ROUTE,
    MAX_RESPONSE_BYTES,
    ODOO_BASE_URL_ENV,
)
from odoo_ai.security import SHARED_SECRET_HEADER

MACHINE_SECRET = "machine-" + "m" * 48


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


def _inventory_response() -> dict[str, object]:
    return {
        "addons_roots": ["/srv/customer/addons"],
        "captured_at": "2026-08-22T10:30:00Z",
        "database": "customer_odoo",
        "installed_modules": ["base", "sale"],
        "ok": True,
        "server_version": "18.0",
    }


def test_machine_only_instance_inventory_is_bounded_and_validated() -> None:
    def responder(request: CapturedRequest) -> ResponseSpec:
        assert request.path == INVENTORY_ROUTE
        assert request.body == b"{}"
        assert request.headers[SHARED_SECRET_HEADER] == MACHINE_SECRET
        assert "X-Odoo-AI-Delegation" not in request.headers
        return _json_response(_inventory_response())

    with fake_odoo_server(responder) as server:
        gateway = _factory(
            f"http://127.0.0.1:{server.server_port}"
        ).for_instance()
        inventory = asyncio.run(gateway.get_instance_inventory())

    assert inventory.database == "customer_odoo"
    assert inventory.installed_modules == ("base", "sale")
    assert inventory.addons_roots == ("/srv/customer/addons",)
    assert MACHINE_SECRET not in repr(gateway)


def test_settings_from_env_accept_nondefault_loopback_url() -> None:
    settings = OdooGatewaySettings.from_env(
        {ODOO_BASE_URL_ENV: "http://127.0.0.1:18069"}
    )

    assert settings.base_url == "http://127.0.0.1:18069"


@pytest.mark.parametrize(
    "value",
    [
        "",
        " http://127.0.0.1:8069",
        "ftp://127.0.0.1:8069",
        "http://user:pass@127.0.0.1:8069",
        "http://127.0.0.1:8069/path",
        "http://127.0.0.1:99999",
    ],
)
def test_invalid_gateway_urls_are_rejected(value: str) -> None:
    with pytest.raises(OdooGatewayError, match="invalid_gateway_url"):
        OdooGatewaySettings(base_url=value)


def test_inventory_rejects_duplicate_or_malformed_values() -> None:
    malformed = _inventory_response()
    malformed["installed_modules"] = ["base", "base"]

    with fake_odoo_server(lambda request: _json_response(malformed)) as server:
        gateway = _factory(
            f"http://127.0.0.1:{server.server_port}"
        ).for_instance()
        with pytest.raises(OdooGatewayError, match="malformed_response"):
            asyncio.run(gateway.get_instance_inventory())


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
        gateway = _factory(
            f"http://127.0.0.1:{server.server_port}"
        ).for_instance()
        with pytest.raises(
            OdooGatewayError,
            match="malformed_response|response_too_large",
        ):
            asyncio.run(gateway.get_instance_inventory())


@pytest.mark.parametrize(
    ("status", "code"),
    [
        (307, "redirect_rejected"),
        (401, "machine_auth_rejected"),
        (403, "machine_auth_rejected"),
        (404, "endpoint_unavailable"),
        (429, "rate_limited"),
        (503, "upstream_unavailable"),
    ],
)
def test_upstream_statuses_map_to_sanitized_errors(status: int, code: str) -> None:
    with fake_odoo_server(lambda request: ResponseSpec(status=status)) as server:
        gateway = _factory(
            f"http://127.0.0.1:{server.server_port}"
        ).for_instance()
        with pytest.raises(OdooGatewayError, match=code) as failure:
            asyncio.run(gateway.get_instance_inventory())

    assert MACHINE_SECRET not in str(failure.value)


def test_timeout_is_sanitized() -> None:
    def responder(request: CapturedRequest) -> ResponseSpec:
        del request
        return ResponseSpec(delay_seconds=0.15)

    with fake_odoo_server(responder) as server:
        gateway = _factory(
            f"http://127.0.0.1:{server.server_port}",
            timeout_seconds=0.02,
        ).for_instance()
        with pytest.raises(OdooGatewayError, match="upstream_timeout") as failure:
            asyncio.run(gateway.get_instance_inventory())

    assert MACHINE_SECRET not in str(failure.value)


def test_adapter_exposes_no_generic_odoo_method() -> None:
    assert not hasattr(HttpOdooInstanceGateway, "execute_kw")
    assert not hasattr(HttpOdooInstanceGateway, "execute_method")
    assert not hasattr(HttpOdooInstanceGateway, "search")
