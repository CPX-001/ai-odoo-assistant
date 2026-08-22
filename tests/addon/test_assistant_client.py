import importlib.util
import json
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
    last_post: dict[str, object] | None = None

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
        elif self.path == "/v1/admin/source/status":
            if self.headers.get("X-Odoo-AI-Shared-Secret") != self.secret:
                self._json(401, b'{"detail":"invalid"}')
            else:
                self._json(
                    200,
                    b'{"state":"DETECTED","scan_status":"succeeded",'
                    b'"scan_id":null,"fingerprint":null,"completed_at":null}',
                )
        else:
            self._json(404, b"{}")

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length))
        type(self).last_post = {
            "headers": dict(self.headers.items()),
            "path": self.path,
            "payload": payload,
        }
        if self.headers.get("X-Odoo-AI-Shared-Secret") != self.secret:
            self._json(401, b'{"error":{"code":"invalid"},"ok":false}')
        elif self.path == "/v1/turns/context-read":
            self._json(200, b'{"ok":true,"turn_id":"example"}')
        elif self.path == "/v1/turns/explain":
            self._json(200, b'{"ok":true,"turn_id":"explain-example"}')
        elif self.path == "/v1/turns/query":
            self._json(200, b'{"ok":true,"turn_id":"query-example"}')
        elif self.path == "/v1/admin/source/rescan":
            self._json(200, b'{"state":"DETECTED","metrics":{}}')
        elif self.path == "/v1/admin/source/test":
            self._json(200, b'{"candidate":{},"excerpt":{}}')
        elif self.path == "/v1/admin/logs/test":
            self._json(200, b'{"state":"OPERATIONAL","provider":"file","results":[]}')
        elif self.path == "/v1/admin/logs/traceback":
            self._json(200, b'{"provider":"file","excerpt":"bounded"}')
        else:
            self._json(404, b"{}")

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
    secret_file.chmod(0o640)
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
    secret_file.chmod(0o640)
    client = AssistantServiceClient(
        base_url=f"http://127.0.0.1:{local_service.server_port}",
        shared_secret_file=str(secret_file),
    )
    with pytest.raises(AssistantServiceError) as rejected:
        client.admin_status()
    assert rejected.value.code == "authentication_rejected"
    assert "wrong" not in str(rejected.value)


def test_client_rejects_unbounded_turn_timeout() -> None:
    with pytest.raises(AssistantServiceError, match="configuration_invalid"):
        AssistantServiceClient(
            base_url="http://127.0.0.1:8000",
            shared_secret_file=None,
            timeout=301,
        )


def test_client_rejects_other_readable_secret(tmp_path: Path) -> None:
    secret_file = tmp_path / "public-secret"
    secret_file.write_text(AssistantHandler.secret, encoding="utf-8")
    secret_file.chmod(0o644)
    client = AssistantServiceClient(
        base_url="http://127.0.0.1:8000",
        shared_secret_file=str(secret_file),
    )

    with pytest.raises(AssistantServiceError) as unavailable:
        client.admin_status()
    assert unavailable.value.code == "authentication_unavailable"


def test_context_read_posts_only_to_the_narrow_authenticated_route(
    tmp_path: Path, local_service: ThreadingHTTPServer
) -> None:
    secret_file = tmp_path / "shared-secret"
    secret_file.write_text(AssistantHandler.secret, encoding="utf-8")
    secret_file.chmod(0o640)
    client = AssistantServiceClient(
        base_url=f"http://127.0.0.1:{local_service.server_port}",
        shared_secret_file=str(secret_file),
    )
    payload = {
        "turn_id": "12345678-1234-5678-1234-567812345678",
        "message": "question",
        "screen": {"model": "sale.order", "res_id": 42},
    }

    response = client.context_read(payload)

    assert response == {"ok": True, "turn_id": "example"}
    assert AssistantHandler.last_post is not None
    assert AssistantHandler.last_post["path"] == "/v1/turns/context-read"
    assert AssistantHandler.last_post["payload"] == payload
    headers = AssistantHandler.last_post["headers"]
    assert headers["X-Odoo-AI-Shared-Secret"] == AssistantHandler.secret
    assert headers["Content-Type"] == "application/json"


def test_explain_posts_only_to_its_narrow_authenticated_route(
    tmp_path: Path, local_service: ThreadingHTTPServer
) -> None:
    secret_file = tmp_path / "shared-secret"
    secret_file.write_text(AssistantHandler.secret, encoding="utf-8")
    secret_file.chmod(0o640)
    client = AssistantServiceClient(
        base_url=f"http://127.0.0.1:{local_service.server_port}",
        shared_secret_file=str(secret_file),
    )
    payload = {
        "turn_id": "12345678-1234-5678-1234-567812345678",
        "message": "explain",
        "screen": {"model": "sale.order", "res_id": 42},
    }

    response = client.explain(payload)

    assert response == {"ok": True, "turn_id": "explain-example"}
    assert AssistantHandler.last_post is not None
    assert AssistantHandler.last_post["path"] == "/v1/turns/explain"
    assert AssistantHandler.last_post["payload"] == payload
    headers = AssistantHandler.last_post["headers"]
    assert headers["X-Odoo-AI-Shared-Secret"] == AssistantHandler.secret


def test_query_posts_only_to_its_narrow_authenticated_route(
    tmp_path: Path, local_service: ThreadingHTTPServer
) -> None:
    secret_file = tmp_path / "shared-secret"
    secret_file.write_text(AssistantHandler.secret, encoding="utf-8")
    secret_file.chmod(0o640)
    client = AssistantServiceClient(
        base_url=f"http://127.0.0.1:{local_service.server_port}",
        shared_secret_file=str(secret_file),
    )
    payload = {
        "turn_id": "12345678-1234-5678-1234-567812345678",
        "message": "query",
        "screen": {"model": "sale.order", "res_id": 42},
    }

    response = client.query(payload)

    assert response == {"ok": True, "turn_id": "query-example"}
    assert AssistantHandler.last_post is not None
    assert AssistantHandler.last_post["path"] == "/v1/turns/query"
    assert AssistantHandler.last_post["payload"] == payload


def test_m3_admin_client_uses_only_fixed_server_side_routes(
    tmp_path: Path, local_service: ThreadingHTTPServer
) -> None:
    secret_file = tmp_path / "shared-secret"
    secret_file.write_text(AssistantHandler.secret, encoding="utf-8")
    secret_file.chmod(0o640)
    client = AssistantServiceClient(
        base_url=f"http://127.0.0.1:{local_service.server_port}",
        shared_secret_file=str(secret_file),
    )

    assert client.source_status()["state"] == "DETECTED"
    assert client.source_rescan()["state"] == "DETECTED"
    assert AssistantHandler.last_post is not None
    assert AssistantHandler.last_post["path"] == "/v1/admin/source/rescan"
    assert AssistantHandler.last_post["payload"] == {}
    assert client.source_test()["candidate"] == {}
    assert (
        client.logs_test({"terms": ["Traceback"], "max_lines": 20, "max_bytes": 4096})[
            "provider"
        ]
        == "file"
    )
    assert client.logs_traceback("sha256:" + "a" * 64, max_bytes=1024) == {
        "provider": "file",
        "excerpt": "bounded",
    }
    assert AssistantHandler.last_post["path"] == "/v1/admin/logs/traceback"
    assert AssistantHandler.last_post["payload"] == {
        "fingerprint": "sha256:" + "a" * 64,
        "max_bytes": 1024,
    }
