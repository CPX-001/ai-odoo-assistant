import importlib.util
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import ModuleType

import pytest


def _load_client_module() -> ModuleType:
    path = Path(__file__).parents[2] / "addons/odoo_ai_assistant/services/assistant_client.py"
    spec = importlib.util.spec_from_file_location("odoo_ai_test_assistant_client", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


client_module = _load_client_module()
AssistantServiceClient = client_module.AssistantServiceClient
AssistantServiceError = client_module.AssistantServiceError


class AssistantHandler(BaseHTTPRequestHandler):
    secret = "addon-test-secret-" + "s" * 48
    last_request: dict[str, object] | None = None

    def do_GET(self) -> None:
        type(self).last_request = {"path": self.path, "headers": dict(self.headers.items())}
        if self.path == "/health":
            self._json(200, {"status": "ok"})
        elif self.headers.get("X-Odoo-AI-Shared-Secret") != self.secret:
            self._json(401, {"error": {"code": "invalid"}, "ok": False})
        elif self.path == "/v1/admin/status":
            self._json(200, {"readiness": "DEGRADED", "components": {}, "instance": None})
        elif self.path == "/v1/admin/source/status":
            self._json(200, {"state": "DETECTED", "scan_status": "succeeded"})
        else:
            self._json(404, {})

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        payload = json.loads(raw) if raw else {}
        type(self).last_request = {"path": self.path, "headers": dict(self.headers.items()), "payload": payload}
        if self.headers.get("X-Odoo-AI-Shared-Secret") != self.secret:
            self._json(401, {"error": {"code": "invalid"}, "ok": False})
        elif self.path == "/v1/admin/maintenance/readiness/test":
            self._json(200, {"operation": "readiness_test", "state": "succeeded", "result_code": "readiness_ok", "checked_at": "2026-08-26T00:00:00Z", "metrics": {}})
        else:
            self._json(404, {})

    def log_message(self, format: str, *args: object) -> None:
        return

    def _json(self, status: int, payload: dict[str, object]) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture
def local_service():
    server = ThreadingHTTPServer(("127.0.0.1", 0), AssistantHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def _client(tmp_path: Path, server: ThreadingHTTPServer) -> AssistantServiceClient:
    secret_file = tmp_path / "shared-secret"
    secret_file.write_text(AssistantHandler.secret, encoding="utf-8")
    secret_file.chmod(0o640)
    return AssistantServiceClient(base_url=f"http://127.0.0.1:{server.server_port}", shared_secret_file=str(secret_file))


def test_client_uses_loopback_and_server_side_secret(tmp_path: Path, local_service: ThreadingHTTPServer) -> None:
    client = _client(tmp_path, local_service)
    assert client.health() == {"status": "ok"}
    assert client.admin_status()["readiness"] == "DEGRADED"
    assert AssistantHandler.last_request is not None
    assert AssistantHandler.last_request["headers"]["X-Odoo-AI-Shared-Secret"] == AssistantHandler.secret


def test_client_rejects_non_loopback_and_unbounded_timeout() -> None:
    with pytest.raises(AssistantServiceError, match="configuration_invalid"):
        AssistantServiceClient(base_url="http://example.com:8000", shared_secret_file=None)
    with pytest.raises(AssistantServiceError, match="configuration_invalid"):
        AssistantServiceClient(base_url="http://127.0.0.1:8000", shared_secret_file=None, timeout=301)


def test_client_rejects_other_readable_secret(tmp_path: Path) -> None:
    secret_file = tmp_path / "public-secret"
    secret_file.write_text(AssistantHandler.secret, encoding="utf-8")
    secret_file.chmod(0o644)
    client = AssistantServiceClient(base_url="http://127.0.0.1:8000", shared_secret_file=str(secret_file))
    with pytest.raises(AssistantServiceError, match="authentication_unavailable"):
        client.admin_status()


def test_current_admin_routes_are_narrow_and_authenticated(tmp_path: Path, local_service: ThreadingHTTPServer) -> None:
    client = _client(tmp_path, local_service)
    assert client.source_status()["state"] == "DETECTED"
    payload = {"actor": {"odoo_uid": 7, "odoo_database": "fixture"}}
    result = client.maintenance_readiness_test(payload)
    assert result["result_code"] == "readiness_ok"
    assert AssistantHandler.last_request is not None
    assert AssistantHandler.last_request["path"] == "/v1/admin/maintenance/readiness/test"
    assert AssistantHandler.last_request["payload"] == payload
