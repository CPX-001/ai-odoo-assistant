"""Bounded effect-free HTTP adapter for Odoo batch preflight."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from http.client import HTTPConnection, HTTPException, HTTPSConnection
from typing import Final
from uuid import UUID

from pydantic import BaseModel, ConfigDict, SecretStr, ValidationError

from odoo_ai.adapters.odoo_http import OdooGatewayError, OdooGatewaySettings
from odoo_ai.contracts.action import ModelName
from odoo_ai.contracts.batch import BatchMutationKind, BatchMutationRequest, SourceRef
from odoo_ai.contracts.batch_preflight import BatchPreflightIssue, BatchPreflightResult
from odoo_ai.security.shared_secret import (
    SHARED_SECRET_HEADER,
    SharedSecretError,
    load_shared_secret,
)

BATCH_PREFLIGHT_ROUTE: Final = "/odoo_ai/internal/v1/batch-preflight"
DELEGATION_HEADER: Final = "X-Odoo-AI-Delegation"
MAX_BATCH_PREFLIGHT_REQUEST_BYTES: Final = 512 * 1024
MAX_BATCH_PREFLIGHT_RESPONSE_BYTES: Final = 128 * 1024
SecretLoader = Callable[[], str]


class _BatchPreflightResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    ok: bool
    operation: BatchMutationKind
    model: ModelName
    accepted_source_refs: tuple[SourceRef, ...] = ()
    issues: tuple[BatchPreflightIssue, ...] = ()


class BatchPreflightOdooGatewayFactory:
    """Bind one ag1 turn token plus machine transport credentials."""

    def __init__(
        self,
        settings: OdooGatewaySettings,
        *,
        secret_loader: SecretLoader = load_shared_secret,
    ) -> None:
        self._settings = settings
        self._secret_loader = secret_loader

    def for_turn(
        self,
        *,
        turn_id: UUID,
        delegation_token: SecretStr | str,
    ) -> HttpBatchPreflightGateway:
        if not isinstance(turn_id, UUID):
            raise OdooGatewayError("invalid_turn_authority")
        token = (
            delegation_token.get_secret_value()
            if isinstance(delegation_token, SecretStr)
            else delegation_token
        )
        _validate_header(token, maximum=8192, error_code="invalid_turn_authority")
        if not token.startswith("ag1."):
            raise OdooGatewayError("invalid_turn_authority")
        try:
            machine_secret = self._secret_loader()
        except SharedSecretError:
            raise OdooGatewayError("machine_auth_unavailable") from None
        _validate_header(machine_secret, maximum=4096, error_code="machine_auth_unavailable")
        return HttpBatchPreflightGateway(
            settings=self._settings,
            turn_id=turn_id,
            delegation_token=token,
            machine_secret=machine_secret,
        )


class HttpBatchPreflightGateway:
    """Send normalized rows to Odoo for validation without granting commit authority."""

    def __init__(
        self,
        *,
        settings: OdooGatewaySettings,
        turn_id: UUID,
        delegation_token: str,
        machine_secret: str,
    ) -> None:
        self._settings = settings
        self._turn_id = turn_id
        self._delegation_token = delegation_token
        self._machine_secret = machine_secret

    async def preflight_batch(self, request: BatchMutationRequest) -> BatchPreflightResult:
        raw = await asyncio.to_thread(
            self._post_json,
            {
                "batch": request.model_dump(mode="json"),
                "turn_id": str(self._turn_id),
            },
        )
        try:
            response = _BatchPreflightResponse.model_validate_json(raw)
            result = BatchPreflightResult(
                operation=response.operation,
                model=response.model,
                accepted_source_refs=response.accepted_source_refs,
                issues=response.issues,
            )
        except (ValidationError, ValueError):
            raise OdooGatewayError("malformed_response") from None
        if response.ok is not True:
            raise OdooGatewayError("malformed_response")
        return result

    def _post_json(self, payload: dict[str, object]) -> bytes:
        body = json.dumps(
            payload,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        if not body or len(body) > MAX_BATCH_PREFLIGHT_REQUEST_BYTES:
            raise OdooGatewayError("request_too_large")
        connection_type = HTTPSConnection if self._settings._scheme == "https" else HTTPConnection
        connection = connection_type(
            self._settings._host,
            self._settings._port,
            timeout=float(self._settings.timeout_seconds),
        )
        try:
            connection.request(
                "POST",
                BATCH_PREFLIGHT_ROUTE,
                body=body,
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    SHARED_SECRET_HEADER: self._machine_secret,
                    DELEGATION_HEADER: self._delegation_token,
                },
            )
            response = connection.getresponse()
            if response.status != 200:
                raise OdooGatewayError(_status_error(response.status))
            content_type = response.getheader("Content-Type", "").partition(";")[0].strip()
            if content_type != "application/json":
                raise OdooGatewayError("malformed_response")
            result = response.read(MAX_BATCH_PREFLIGHT_RESPONSE_BYTES + 1)
            if len(result) > MAX_BATCH_PREFLIGHT_RESPONSE_BYTES:
                raise OdooGatewayError("response_too_large")
            if not result:
                raise OdooGatewayError("malformed_response")
            return result
        except OdooGatewayError:
            raise
        except TimeoutError:
            raise OdooGatewayError("upstream_timeout") from None
        except (HTTPException, OSError):
            raise OdooGatewayError("upstream_unavailable") from None
        finally:
            connection.close()


def _validate_header(value: object, *, maximum: int, error_code: str) -> None:
    if (
        not isinstance(value, str)
        or not 1 <= len(value) <= maximum
        or value != value.strip()
        or any(ord(character) < 33 or ord(character) > 126 for character in value)
    ):
        raise OdooGatewayError(error_code)


def _status_error(status: int) -> str:
    if status in {401, 403}:
        return "access_denied"
    if status == 413:
        return "request_too_large"
    if status in {400, 415, 422}:
        return "invalid_request"
    if status in {502, 503, 504}:
        return "upstream_unavailable"
    return "upstream_error"
