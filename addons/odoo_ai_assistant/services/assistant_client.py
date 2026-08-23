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
        if (
            isinstance(timeout, bool)
            or not isinstance(timeout, (int, float))
            or not 0 < timeout <= 300
        ):
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

    def diagnostics_matrix(self) -> dict[str, Any]:
        """Read the versioned M7 administrator diagnostics matrix."""

        return self._admin_get("/v1/admin/diagnostics")

    def maintenance_status(self) -> dict[str, Any]:
        return self._admin_get("/v1/admin/maintenance/status")

    def maintenance_readiness_test(self, payload: dict[str, object]) -> dict[str, Any]:
        return self._admin_post("/v1/admin/maintenance/readiness/test", payload)

    def maintenance_source_rescan(self, payload: dict[str, object]) -> dict[str, Any]:
        return self._admin_post("/v1/admin/maintenance/source/rescan", payload)

    def maintenance_source_test(self, payload: dict[str, object]) -> dict[str, Any]:
        return self._admin_post("/v1/admin/maintenance/source/test", payload)

    def maintenance_logs_test(self, payload: dict[str, object]) -> dict[str, Any]:
        return self._admin_post("/v1/admin/maintenance/logs/test", payload)

    def maintenance_knowledge_reindex(self, payload: dict[str, object]) -> dict[str, Any]:
        return self._admin_post("/v1/admin/maintenance/knowledge/reindex", payload)

    def maintenance_reasoning_test(self, payload: dict[str, object]) -> dict[str, Any]:
        return self._admin_post("/v1/admin/maintenance/reasoning/test", payload)

    def maintenance_action_self_test(self, payload: dict[str, object]) -> dict[str, Any]:
        return self._admin_post("/v1/admin/maintenance/action/self-test", payload)

    def maintenance_configuration_revalidate(
        self, payload: dict[str, object]
    ) -> dict[str, Any]:
        return self._admin_post(
            "/v1/admin/maintenance/configuration/revalidate",
            payload,
        )

    def configuration_snapshot(self) -> dict[str, Any]:
        """Read the sanitized M7 configuration snapshot server-to-server."""

        return self._admin_get("/v1/admin/configuration")

    def configuration_validate(self, payload: dict[str, object]) -> dict[str, Any]:
        """Validate only the closed ADMIN_MUTABLE configuration payload."""

        return self._admin_post("/v1/admin/configuration/validate", payload)

    def configuration_apply(self, payload: dict[str, object]) -> dict[str, Any]:
        """Apply one revision-guarded ADMIN_MUTABLE configuration payload."""

        return self._admin_post("/v1/admin/configuration/apply", payload)

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

        return self._turn_post("/v1/turns/context-read", payload)

    def explain(self, payload: dict[str, object]) -> dict[str, Any]:
        """Submit one bounded server-to-server M4 EXPLAIN turn."""

        return self._turn_post("/v1/turns/explain", payload)

    def query(self, payload: dict[str, object]) -> dict[str, Any]:
        """Submit one bounded server-to-server M5 QUERY turn."""

        return self._turn_post("/v1/turns/query", payload)

    def how_to(self, payload: dict[str, object]) -> dict[str, Any]:
        """Submit one bounded server-to-server M5 HOW_TO turn."""

        return self._turn_post("/v1/turns/how-to", payload)

    def action(self, payload: dict[str, object]) -> dict[str, Any]:
        """Submit one p1-bound preview-only ACTION turn."""

        return self._turn_post("/v1/turns/action", payload)

    def action_decision(self, payload: dict[str, object]) -> dict[str, Any]:
        """Submit one host-derived approve/reject command outside reasoning."""

        return self._admin_post("/v1/actions/decision-execute", payload)

    def _turn_post(
        self, path: str, payload: dict[str, object]
    ) -> dict[str, Any]:
        if path not in {
            "/v1/turns/context-read",
            "/v1/turns/explain",
            "/v1/turns/how-to",
            "/v1/turns/query",
            "/v1/turns/action",
        }:
            raise AssistantServiceError("invalid_request")

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
            path,
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
            if _response_error_code(response_body) == "approval_binding_mismatch":
                raise AssistantServiceError("approval_binding_mismatch")
            raise AssistantServiceError("access_denied")
        if response.status in {404, 409, 410, 422}:
            error_code = _response_error_code(response_body)
            action_codes = {
                "action_budget_exceeded",
                "action_rejected",
                "approval_binding_mismatch",
                "approval_expired",
                "approval_not_found",
                "proposal_already_decided",
                "proposal_not_found",
                "record_context_required",
            }
            configuration_codes = {
                "configuration_invalid",
                "configuration_revision_conflict",
            }
            maintenance_codes = {
                "maintenance_invalid",
                "maintenance_job_active",
                "maintenance_job_not_found",
                "maintenance_unavailable",
            }
            if error_code in action_codes | configuration_codes | maintenance_codes:
                raise AssistantServiceError(error_code)
            if response.status == 404:
                raise AssistantServiceError("diagnostic_not_found")
            if response.status == 409:
                raise AssistantServiceError("diagnostic_unavailable")
            if response.status == 410:
                raise AssistantServiceError("action_rejected")
        if response.status == 413:
            raise AssistantServiceError("invalid_request")
        if response.status == 422:
            if _response_error_code(response_body) == "query_rejected":
                raise AssistantServiceError("query_rejected")
            raise AssistantServiceError("invalid_context")
        if response.status in {502, 503, 504}:
            error_code = _response_error_code(response_body)
            if error_code in {
                "engine_timeout",
                "engine_unavailable",
                "evidence_unavailable",
                "maintenance_unavailable",
                "query_budget_exceeded",
            }:
                raise AssistantServiceError(error_code)
            raise AssistantServiceError("service_unavailable")
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


def _response_error_code(value: bytes) -> str | None:
    try:
        payload = json.loads(value)
    except (UnicodeError, ValueError):
        return None
    if not isinstance(payload, dict) or set(payload) != {"error", "ok"}:
        return None
    error = payload.get("error")
    if payload.get("ok") is not False or not isinstance(error, dict):
        return None
    code = error.get("code")
    return code if isinstance(code, str) else None
