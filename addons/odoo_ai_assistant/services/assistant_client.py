"""Narrow server-side HTTP client for the local Assistant Service."""

from __future__ import annotations

import http.client
import ipaddress
import json
import stat
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

MAX_RESPONSE_BYTES = 64 * 1024
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

    def _read_shared_secret(self) -> str:
        if not self._shared_secret_file:
            raise AssistantServiceError("authentication_unconfigured")
        path = Path(self._shared_secret_file)
        try:
            metadata = path.stat()
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > 4096:
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
        connection = http.client.HTTPConnection(self._host, self._port, timeout=self._timeout)
        try:
            connection.request("GET", path, headers=headers or {})
            response = connection.getresponse()
            body = response.read(MAX_RESPONSE_BYTES + 1)
        except OSError as error:
            raise AssistantServiceError("service_unavailable") from error
        finally:
            connection.close()
        if response.status == 401:
            raise AssistantServiceError("authentication_rejected")
        if response.status != 200 or len(body) > MAX_RESPONSE_BYTES:
            raise AssistantServiceError("invalid_response")
        try:
            payload = json.loads(body)
        except (UnicodeError, ValueError) as error:
            raise AssistantServiceError("invalid_response") from error
        if not isinstance(payload, dict):
            raise AssistantServiceError("invalid_response")
        return payload
