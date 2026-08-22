"""Narrow server-side HTTP client for the local Assistant Service."""

from __future__ import annotations

import http.client
import ipaddress
import json
import stat
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

MAX_REQUEST_BYTES = 16 * 1024
MAX_RESPONSE_BYTES = 128 * 1024
SHARED_SECRET_HEADER = "X-Odoo-AI-Shared-Secret"


class AssistantServiceError(RuntimeError):
    """Sanitized client failure safe to map to an administrator message."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class AssistantServiceClient:
    def __init__(
        self,
        *,
        base_url: str,
        shared_secret_file: str | None,
        timeout: float = 3.0,
    ) -> None:
        parsed = urlsplit(base_url.strip())
        if (
            parsed.scheme != "http"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            raise AssistantServiceError("configuration_invalid")
        try:
            loopback = (
                parsed.hostname == "localhost"
                or ipaddress.ip_address(parsed.hostname).is_loopback
            )
            port = parsed.port or 80
        except ValueError as error:
            raise AssistantServiceError("configuration_invalid") from error
        if not loopback or not 1 <= port <= 65535:
            raise AssistantServiceError("configuration_invalid")
        self._host = parsed.hostname
        self._port = port
        self._shared_secret_file = shared_secret_file
        self._timeout = timeout

    def health(self) -> dict[str, Any]:
        payload = self._get_json("/health")
        if payload.get("status") != "ok":
            raise AssistantServiceError("invalid_response")
        return payload

    def admin_status(self) -> dict[str, Any]:
        secret = self._read_shared_secret()
        return self._get_json(
            "/v1/admin/status", headers={SHARED_SECRET_HEADER: secret}
        )

    def source_status(self) -> dict[str, Any]:
        return self._admin_get("/v1/admin/source/status")

    def source_rescan(self) -> dict[str, Any]:
        return self._admin_post("/v1/admin/source/rescan", {})

    def source_test(self) -> dict[str, Any]:
        return self._admin_post("/v1/admin/source/test", {})

    def logs_test(self, payload: dict[str, object]) -> dict[str, Any]:
        return self._admin_post("/v1/admin/logs/test", payload)

    def logs_traceback(self, fingerprint: str, *, max_bytes: int) -> dict[str, Any]:
        return self._admin_post(
            "/v1/admin/logs/traceback",
            {"fingerprint": fingerprint, "max_bytes": max_bytes},
        )

    def context_read(self, payload: dict[str, object]) -> dict[str, Any]:
        """Submit one bounded server-to-server M2 contextual read turn."""

        secret = self._read_shared_secret()
        try:
            body = json.dumps(
                payload,
                allow_nan=False,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        except (TypeError, ValueError) as error:
            raise AssistantServiceError("invalid_request") from error
        if not body or len(body) > MAX_REQUEST_BYTES:
            raise AssistantServiceError("invalid_request")
        return self._request_json(
            "POST",
            "/v1/turns/context-read",
            body=body,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                SHARED_SECRET_HEADER: secret,
            },
        )

    def _read_shared_secret(self) -> str:
        if not self._shared_secret_file:
            raise AssistantServiceError("authentication_unconfigured")
        path = Path(self._shared_secret_file)
        try:
            metadata = path.stat()
            if (
                not stat.S_ISREG(metadata.st_mode)
                or metadata.st_size > 4096
                or metadata.st_mode & 0o007
            ):
                raise OSError
            secret = path.read_text(encoding="utf-8").strip()
        except (OSError, UnicodeError) as error:
            raise AssistantServiceError("authentication_unavailable") from error
        if len(secret) < 43:
            raise AssistantServiceError("authentication_unavailable")
        return secret

    def _get_json(
        self, path: str, *, headers: dict[str, str] | None = None
    ) -> dict[str, Any]:
        return self._request_json("GET", path, headers=headers)

    def _admin_get(self, path: str) -> dict[str, Any]:
        secret = self._read_shared_secret()
        return self._get_json(path, headers={SHARED_SECRET_HEADER: secret})

    def _admin_post(
        self, path: str, payload: dict[str, object]
    ) -> dict[str, Any]:
        secret = self._read_shared_secret()
        try:
            body = json.dumps(
                payload,
                allow_nan=False,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        except (TypeError, ValueError) as error:
            raise AssistantServiceError("invalid_request") from error
        if len(body) > MAX_REQUEST_BYTES:
            raise AssistantServiceError("invalid_request")
        return self._request_json(
            "POST",
            path,
            body=body,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                SHARED_SECRET_HEADER: secret,
            },
        )

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        body: bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        connection = http.client.HTTPConnection(self._host, self._port, timeout=self._timeout)
        try:
            connection.request(method, path, body=body, headers=headers or {})
            response = connection.getresponse()
            response_body = response.read(MAX_RESPONSE_BYTES + 1)
        except OSError as error:
            raise AssistantServiceError("service_unavailable") from error
        finally:
            connection.close()
        if response.status == 401:
            raise AssistantServiceError("authentication_rejected")
        if response.status == 403:
            raise AssistantServiceError("access_denied")
        if response.status == 404:
            raise AssistantServiceError("diagnostic_not_found")
        if response.status == 409:
            raise AssistantServiceError("diagnostic_unavailable")
        if response.status == 413:
            raise AssistantServiceError("invalid_request")
        if response.status == 422:
            raise AssistantServiceError("invalid_context")
        if response.status >= 500:
            raise AssistantServiceError("service_unavailable")
        content_type = response.getheader("Content-Type", "").partition(";")[0].strip()
        if (
            response.status != 200
            or content_type != "application/json"
            or len(response_body) > MAX_RESPONSE_BYTES
        ):
            raise AssistantServiceError("invalid_response")
        try:
            response_payload = json.loads(response_body)
        except (UnicodeError, ValueError) as error:
            raise AssistantServiceError("invalid_response") from error
        if not isinstance(response_payload, dict):
            raise AssistantServiceError("invalid_response")
        return response_payload
