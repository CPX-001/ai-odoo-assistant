import importlib.util
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import ModuleType

import pytest


def _load_client_module() -> ModuleType:
    path = (
        Path(__file__).parents[2]
        / "addons/odoo_ai_assistant/services/assistant_client.py"
    )
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

    def do_GET(self) -> None:
        if self.path == "/health":
            self._json(200, b'{"status":"ok"}')
        elif self.path == "/v1/admin/status":
            if self.headers.get("X-Odoo-AI-Shared-Secret") != self.secret:
                self._json(401, b'{"detail":"invalid"}')
            else:
                self._json(
                    200,
                    b'{"readiness":"DEGRADED","components":{},"instance":null}',
                )
        else:
            self._json(404, b'{}')

    def log_message(self, format: str, *args: object) -> None:
        return

    def _json(self, status: int, body: bytes) -> None:
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


def test_client_uses_non_default_local_port_and_server_side_secret(
    tmp_path: Path, local_service: ThreadingHTTPServer
) -> None:
    secret_file = tmp_path / "shared-secret"
    secret_file.write_text(f"{AssistantHandler.secret}\n", encoding="utf-8")
    client = AssistantServiceClient(
        base_url=f"http://127.0.0.1:{local_service.server_port}",
        shared_secret_file=str(secret_file),
    )

    assert client.health() == {"status": "ok"}
    assert client.admin_status()["readiness"] == "DEGRADED"


def test_client_rejects_non_loopback_and_sanitizes_auth_failure(
    tmp_path: Path, local_service: ThreadingHTTPServer
) -> None:
    with pytest.raises(AssistantServiceError) as public:
        AssistantServiceClient(
            base_url="http://example.com:8000", shared_secret_file=None
        )
    assert public.value.code == "configuration_invalid"

    secret_file = tmp_path / "shared-secret"
    secret_file.write_text("wrong-" + "x" * 48, encoding="utf-8")
    client = AssistantServiceClient(
        base_url=f"http://127.0.0.1:{local_service.server_port}",
        shared_secret_file=str(secret_file),
    )
    with pytest.raises(AssistantServiceError) as rejected:
        client.admin_status()
    assert rejected.value.code == "authentication_rejected"
    assert "wrong" not in str(rejected.value)
