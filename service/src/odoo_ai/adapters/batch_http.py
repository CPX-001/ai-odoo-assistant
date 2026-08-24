"""Signed bounded HTTP adapter for idempotent Odoo batch chunks."""

from __future__ import annotations

import asyncio
import json
import secrets
import time
from collections.abc import Callable, Mapping
from http.client import HTTPConnection, HTTPException, HTTPSConnection
from typing import Final

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from odoo_ai.application.batch_authority import batch_chunk_fingerprint
from odoo_ai.contracts.batch import (
    BatchCreateItem,
    BatchDeleteItem,
    BatchFailureMode,
    BatchItemResult,
    BatchMutationKind,
    BatchMutationRequest,
    BatchPatchItem,
)
from odoo_ai.contracts.batch_authority import BatchAuthorityClaims
from odoo_ai.contracts.batch_job import BatchExecutionContext
from odoo_ai.security.batch_authority import BatchAuthorityCodec, BatchAuthorityError
from odoo_ai.security.shared_secret import (
    SHARED_SECRET_HEADER,
    SharedSecretError,
    load_shared_secret,
)
from odoo_ai.adapters.odoo_http import OdooGatewayError, OdooGatewaySettings

BATCH_COMMIT_ROUTE: Final = "/odoo_ai/internal/v1/batch-commit"
DELEGATION_HEADER: Final = "X-Odoo-AI-Delegation"
MAX_BATCH_REQUEST_BYTES: Final = 512 * 1024
MAX_BATCH_RESPONSE_BYTES: Final = 256 * 1024
BATCH_TOKEN_TTL_SECONDS: Final = 60
SecretLoader = Callable[[], str]


class _BatchCommitResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    ok: bool
    job_id: str = Field(min_length=36, max_length=36)
    attempt_id: str = Field(min_length=36, max_length=36)
    chunk_fingerprint: str = Field(
        pattern=r"^batch-chunk:v1:sha256:[0-9a-f]{64}$"
    )
    results: tuple[BatchItemResult, ...] = Field(min_length=1, max_length=200)


class BatchOdooGatewayFactory:
    """Build a gateway from host-owned transport credentials and b1 signing key."""

    def __init__(
        self,
        settings: OdooGatewaySettings,
        *,
        authority_codec: BatchAuthorityCodec,
        secret_loader: SecretLoader = load_shared_secret,
    ) -> None:
        self._settings = settings
        self._authority_codec = authority_codec
        self._secret_loader = secret_loader

    @classmethod
    def from_env(
        cls,
        environ: Mapping[str, str] | None = None,
    ) -> BatchOdooGatewayFactory:
        return cls(
            OdooGatewaySettings.from_env(environ),
            authority_codec=BatchAuthorityCodec.from_env(environ),
        )

    def build(self) -> HttpBatchMutationGateway:
        try:
            machine_secret = self._secret_loader()
        except SharedSecretError:
            raise OdooGatewayError("machine_auth_unavailable") from None
        if not isinstance(machine_secret, str) or not 1 <= len(machine_secret) <= 4096:
            raise OdooGatewayError("machine_auth_unavailable")
        return HttpBatchMutationGateway(
            settings=self._settings,
            authority_codec=self._authority_codec,
            machine_secret=machine_secret,
        )


class HttpBatchMutationGateway:
    def __init__(
        self,
        *,
        settings: OdooGatewaySettings,
        authority_codec: BatchAuthorityCodec,
        machine_secret: str,
    ) -> None:
        self._settings = settings
        self._codec = authority_codec
        self._machine_secret = machine_secret

    async def create_many(
        self,
        *,
        context: BatchExecutionContext,
        model: str,
        schema_id: str,
        items: tuple[BatchCreateItem, ...],
        failure_mode: BatchFailureMode,
    ) -> tuple[BatchItemResult, ...]:
        request = BatchMutationRequest(
            operation=BatchMutationKind.CREATE,
            model=model,
            schema_id=schema_id,
            failure_mode=failure_mode,
            items=items,
        )
        return await self._commit(context, request)

    async def patch_many(
        self,
        *,
        context: BatchExecutionContext,
        model: str,
        schema_id: str,
        items: tuple[BatchPatchItem, ...],
        failure_mode: BatchFailureMode,
    ) -> tuple[BatchItemResult, ...]:
        request = BatchMutationRequest(
            operation=BatchMutationKind.PATCH,
            model=model,
            schema_id=schema_id,
            failure_mode=failure_mode,
            items=items,
        )
        return await self._commit(context, request)

    async def delete_many(
        self,
        *,
        context: BatchExecutionContext,
        model: str,
        items: tuple[BatchDeleteItem, ...],
        failure_mode: BatchFailureMode,
    ) -> tuple[BatchItemResult, ...]:
        request = BatchMutationRequest(
            operation=BatchMutationKind.DELETE,
            model=model,
            failure_mode=failure_mode,
            items=items,
        )
        return await self._commit(context, request)

    async def _commit(
        self,
        context: BatchExecutionContext,
        request: BatchMutationRequest,
    ) -> tuple[BatchItemResult, ...]:
        chunk_fingerprint = batch_chunk_fingerprint(request)
        fields = _chunk_fields(request)
        now = int(time.time())
        try:
            token = self._codec.encode(
                BatchAuthorityClaims(
                    jti=secrets.token_urlsafe(18),
                    job_id=context.job_id,
                    attempt_id=context.attempt_id,
                    authorization_id=context.authorization_id,
                    job_fingerprint=context.job_fingerprint,
                    chunk_fingerprint=chunk_fingerprint,
                    instance_id=context.instance_id,
                    database=context.database,
                    uid=context.uid,
                    company_id=context.company_id,
                    allowed_company_ids=context.allowed_company_ids,
                    operation=request.operation,
                    model=request.model,
                    schema_id=request.schema_id,
                    fields=fields,
                    failure_mode=request.failure_mode,
                    policy_revision=context.policy_revision,
                    row_count=len(request.items),
                    issued_at=now,
                    expires_at=now + BATCH_TOKEN_TTL_SECONDS,
                )
            )
        except (BatchAuthorityError, ValueError):
            raise OdooGatewayError("batch_authority_unavailable") from None
        raw = await asyncio.to_thread(
            self._post_json,
            token,
            {"batch": request.model_dump(mode="json")},
        )
        try:
            response = _BatchCommitResponse.model_validate_json(raw)
        except ValidationError:
            raise OdooGatewayError("malformed_response") from None
        if (
            response.ok is not True
            or response.job_id != str(context.job_id)
            or response.attempt_id != str(context.attempt_id)
            or response.chunk_fingerprint != chunk_fingerprint
            or tuple(item.source_ref for item in response.results)
            != tuple(item.source_ref for item in request.items)
        ):
            raise OdooGatewayError("malformed_response")
        return response.results

    def _post_json(self, authority_token: str, payload: dict[str, object]) -> bytes:
        body = json.dumps(
            payload,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        if len(body) > MAX_BATCH_REQUEST_BYTES:
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
                BATCH_COMMIT_ROUTE,
                body=body,
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    SHARED_SECRET_HEADER: self._machine_secret,
                    DELEGATION_HEADER: authority_token,
                },
            )
            response = connection.getresponse()
            if response.status != 200:
                raise OdooGatewayError(_status_error(response.status))
            content_type = response.getheader("Content-Type", "").partition(";")[0].strip()
            if content_type != "application/json":
                raise OdooGatewayError("malformed_response")
            result = response.read(MAX_BATCH_RESPONSE_BYTES + 1)
            if len(result) > MAX_BATCH_RESPONSE_BYTES:
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


def _chunk_fields(request: BatchMutationRequest) -> tuple[str, ...]:
    fields: set[str] = set()
    for item in request.items:
        if isinstance(item, BatchCreateItem):
            fields.update(value.field for value in item.values)
        elif isinstance(item, BatchPatchItem):
            fields.update(value.field for value in item.changes)
    return tuple(sorted(fields))


def _status_error(status: int) -> str:
    if status in {401, 403}:
        return "access_denied"
    if status == 409:
        return "batch_rejected"
    if status == 413:
        return "request_too_large"
    if status in {400, 422}:
        return "invalid_request"
    if status in {502, 503, 504}:
        return "upstream_unavailable"
    return "upstream_error"
