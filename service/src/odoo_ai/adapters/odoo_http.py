"""Narrow per-turn HTTP implementation of the OdooGateway port."""

from __future__ import annotations

import asyncio
import json
import os
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from http.client import HTTPConnection, HTTPException, HTTPResponse, HTTPSConnection
from typing import Annotated, Final, Literal, cast
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID, uuid4

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    SecretStr,
    ValidationError,
    field_validator,
)

from odoo_ai.contracts import (
    Evidence,
    EvidenceKind,
    EvidenceSensitivity,
    EvidenceStatus,
    RecordRef,
    RecordSnapshot,
)
from odoo_ai.security import SHARED_SECRET_HEADER, SharedSecretError, load_shared_secret

ODOO_BASE_URL_ENV: Final = "ODOO_AI_ODOO_BASE_URL"
DELEGATION_HEADER: Final = "X-Odoo-AI-Delegation"
METADATA_ROUTE: Final = "/odoo_ai/internal/v1/model-metadata"
READ_ROUTE: Final = "/odoo_ai/internal/v1/read-records"
DEFAULT_TIMEOUT_SECONDS: Final = 2.0
MAX_REQUEST_BYTES: Final = 32 * 1024
MAX_RESPONSE_BYTES: Final = 128 * 1024
MAX_RECORDS: Final = 8
MAX_FIELDS: Final = 64

_MODEL_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]{0,127}$")
_FIELD_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")
_METADATA_ATTRIBUTES = frozenset(
    {"type", "string", "required", "readonly", "relation", "selection"}
)

PositiveId = Annotated[int, Field(strict=True, gt=0)]
BoundedText = Annotated[str, Field(max_length=32 * 1024)]
SecretLoader = Callable[[], str]


class OdooGatewayError(RuntimeError):
    """Sanitized adapter failure that contains no endpoint or credential data."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class OdooGatewaySettings:
    """Validated server-side routing and transport limits for Odoo callbacks."""

    base_url: str
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    max_request_bytes: int = MAX_REQUEST_BYTES
    max_response_bytes: int = MAX_RESPONSE_BYTES
    _scheme: str = field(init=False, repr=False)
    _host: str = field(init=False, repr=False)
    _port: int = field(init=False, repr=False)

    def __post_init__(self) -> None:
        scheme, host, port, normalized = _validate_base_url(self.base_url)
        if (
            isinstance(self.timeout_seconds, bool)
            or not isinstance(self.timeout_seconds, (int, float))
            or not 0 < self.timeout_seconds <= 30
        ):
            raise OdooGatewayError("invalid_configuration")
        if (
            type(self.max_request_bytes) is not int
            or not 1 <= self.max_request_bytes <= MAX_REQUEST_BYTES
            or type(self.max_response_bytes) is not int
            or not 1 <= self.max_response_bytes <= MAX_RESPONSE_BYTES
        ):
            raise OdooGatewayError("invalid_configuration")
        object.__setattr__(self, "base_url", normalized)
        object.__setattr__(self, "_scheme", scheme)
        object.__setattr__(self, "_host", host)
        object.__setattr__(self, "_port", port)

    @classmethod
    def from_env(
        cls, environ: Mapping[str, str] | None = None
    ) -> OdooGatewaySettings:
        source = os.environ if environ is None else environ
        raw_url = source.get(ODOO_BASE_URL_ENV, "")
        if not raw_url:
            raise OdooGatewayError("gateway_unconfigured")
        return cls(base_url=raw_url)


class OdooGatewayFactory:
    """Bind transport configuration and both credentials to one turn."""

    __slots__ = ("_secret_loader", "_settings")

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
    ) -> HttpOdooGateway:
        if not isinstance(turn_id, UUID):
            raise OdooGatewayError("invalid_turn_authority")
        token = (
            delegation_token.get_secret_value()
            if isinstance(delegation_token, SecretStr)
            else delegation_token
        )
        _validate_header_secret(token, maximum=4096)
        try:
            machine_secret = self._secret_loader()
        except SharedSecretError:
            raise OdooGatewayError("machine_auth_unavailable") from None
        _validate_header_secret(machine_secret, maximum=4096)
        return HttpOdooGateway(
            settings=self._settings,
            turn_id=turn_id,
            delegation_token=token,
            machine_secret=machine_secret,
        )


class HttpOdooGateway:
    """Call exactly the two delegated Odoo read handlers for a single turn."""

    __slots__ = ("_delegation_token", "_machine_secret", "_settings", "_turn_id")

    def __init__(
        self,
        *,
        settings: OdooGatewaySettings,
        turn_id: UUID,
        delegation_token: str,
        machine_secret: str,
    ) -> None:
        if not isinstance(settings, OdooGatewaySettings) or not isinstance(turn_id, UUID):
            raise OdooGatewayError("invalid_turn_authority")
        _validate_header_secret(delegation_token, maximum=4096)
        _validate_header_secret(machine_secret, maximum=4096)
        self._settings = settings
        self._turn_id = turn_id
        self._delegation_token = delegation_token
        self._machine_secret = machine_secret

    def __repr__(self) -> str:
        return (
            f"{type(self).__name__}(base_url={self._settings.base_url!r}, "
            f"turn_id={self._turn_id!s}, credentials=<redacted>)"
        )

    async def get_model_metadata(self, model: str) -> Evidence:
        parsed_model = _model_name(model)
        raw = await asyncio.to_thread(
            self._post_json,
            METADATA_ROUTE,
            {"model": parsed_model, "turn_id": str(self._turn_id)},
        )
        try:
            response = _MetadataResponse.model_validate_json(raw)
        except ValidationError:
            raise OdooGatewayError("malformed_response") from None
        if response.model != parsed_model:
            raise OdooGatewayError("malformed_response")
        return Evidence(
            evidence_id=uuid4(),
            kind=EvidenceKind.METADATA,
            status=EvidenceStatus.CHECKED,
            title=f"Odoo model metadata: {parsed_model}",
            summary="Metadata read under the delegated Odoo user.",
            payload={
                "fields": cast(JsonValue, response.fields),
                "model": response.model,
            },
            pointer={"model": parsed_model, "provider": "odoo_http"},
            observed_at=response.captured_at,
            sensitivity=EvidenceSensitivity.TECHNICAL,
        )

    async def read_records(
        self,
        records: list[RecordRef],
        fields: list[str],
    ) -> list[RecordSnapshot]:
        model, record_ids = _record_request(records)
        parsed_fields = _field_names(fields)
        raw = await asyncio.to_thread(
            self._post_json,
            READ_ROUTE,
            {
                "fields": list(parsed_fields),
                "ids": list(record_ids),
                "model": model,
                "turn_id": str(self._turn_id),
            },
        )
        try:
            response = _ReadResponse.model_validate_json(raw)
        except ValidationError:
            raise OdooGatewayError("malformed_response") from None
        if response.model != model:
            raise OdooGatewayError("malformed_response")
        rows = {row.id: row for row in response.records}
        if len(rows) != len(response.records) or set(rows) != set(record_ids) or any(
            set(row.fields) != set(parsed_fields) for row in response.records
        ):
            raise OdooGatewayError("malformed_response")
        return [
            RecordSnapshot(
                record=RecordRef(
                    model=model,
                    id=record_id,
                    display_name=rows[record_id].display_name,
                ),
                fields=rows[record_id].fields,
                captured_at=response.captured_at,
                provenance={"model": model, "provider": "odoo_http"},
            )
            for record_id in record_ids
        ]

    def _post_json(self, route: str, payload: dict[str, object]) -> bytes:
        try:
            body = json.dumps(
                payload,
                allow_nan=False,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        except (TypeError, ValueError):
            raise OdooGatewayError("invalid_request") from None
        if len(body) > self._settings.max_request_bytes:
            raise OdooGatewayError("request_too_large")

        connection_type = (
            HTTPSConnection if self._settings._scheme == "https" else HTTPConnection
        )
        connection = connection_type(
            self._settings._host,
            self._settings._port,
            timeout=float(self._settings.timeout_seconds),
        )
        try:
            connection.request(
                "POST",
                route,
                body=body,
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    DELEGATION_HEADER: self._delegation_token,
                    SHARED_SECRET_HEADER: self._machine_secret,
                },
            )
            response = connection.getresponse()
            return self._read_response(response)
        except OdooGatewayError:
            raise
        except TimeoutError:
            raise OdooGatewayError("upstream_timeout") from None
        except (HTTPException, OSError):
            raise OdooGatewayError("upstream_unavailable") from None
        finally:
            connection.close()

    def _read_response(self, response: HTTPResponse) -> bytes:
        if response.status != 200:
            raise OdooGatewayError(_status_error(response.status))
        content_type = response.getheader("Content-Type", "").partition(";")[0].strip()
        if content_type != "application/json":
            raise OdooGatewayError("malformed_response")
        body = response.read(self._settings.max_response_bytes + 1)
        if len(body) > self._settings.max_response_bytes:
            raise OdooGatewayError("response_too_large")
        if not body:
            raise OdooGatewayError("malformed_response")
        return body


class _MetadataResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    captured_at: AwareDatetime
    fields: dict[str, dict[str, JsonValue]] = Field(max_length=MAX_FIELDS)
    model: str = Field(min_length=1, max_length=128)
    ok: Literal[True]

    @field_validator("fields")
    @classmethod
    def validate_fields(
        cls, value: dict[str, dict[str, JsonValue]]
    ) -> dict[str, dict[str, JsonValue]]:
        for name, description in value.items():
            if not _FIELD_PATTERN.fullmatch(name):
                raise ValueError("invalid metadata field")
            _validate_metadata_description(description)
        return value


class _RecordResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    display_name: BoundedText | None
    fields: dict[str, JsonValue] = Field(max_length=MAX_FIELDS)
    id: PositiveId

    @field_validator("fields")
    @classmethod
    def validate_fields(cls, value: dict[str, JsonValue]) -> dict[str, JsonValue]:
        if any(not _FIELD_PATTERN.fullmatch(name) for name in value):
            raise ValueError("invalid record field")
        return value


class _ReadResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    captured_at: AwareDatetime
    model: str = Field(min_length=1, max_length=128)
    ok: Literal[True]
    records: list[_RecordResponse] = Field(min_length=1, max_length=MAX_RECORDS)


def _validate_base_url(value: object) -> tuple[str, str, int, str]:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or any(character.isspace() or ord(character) < 32 for character in value)
    ):
        raise OdooGatewayError("invalid_gateway_url")
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        raise OdooGatewayError("invalid_gateway_url") from None
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise OdooGatewayError("invalid_gateway_url")
    try:
        host = parsed.hostname.encode("idna").decode("ascii")
    except UnicodeError:
        raise OdooGatewayError("invalid_gateway_url") from None
    if not host or any(character.isspace() or ord(character) < 32 for character in host):
        raise OdooGatewayError("invalid_gateway_url")
    effective_port = port or (443 if parsed.scheme == "https" else 80)
    if not 1 <= effective_port <= 65535:
        raise OdooGatewayError("invalid_gateway_url")
    display_host = f"[{host}]" if ":" in host else host
    display_port = "" if port is None else f":{port}"
    normalized = urlunsplit((parsed.scheme, f"{display_host}{display_port}", "", "", ""))
    return parsed.scheme, host, effective_port, normalized


def _validate_header_secret(value: object, *, maximum: int) -> None:
    if (
        not isinstance(value, str)
        or not 1 <= len(value) <= maximum
        or any(ord(character) < 33 or ord(character) > 126 for character in value)
    ):
        raise OdooGatewayError("invalid_turn_authority")


def _model_name(value: object) -> str:
    if not isinstance(value, str) or not _MODEL_PATTERN.fullmatch(value):
        raise OdooGatewayError("invalid_request")
    return value


def _record_request(records: object) -> tuple[str, tuple[int, ...]]:
    if not isinstance(records, list) or not 1 <= len(records) <= MAX_RECORDS:
        raise OdooGatewayError("invalid_request")
    if not all(isinstance(record, RecordRef) for record in records):
        raise OdooGatewayError("invalid_request")
    model = _model_name(records[0].model)
    if any(record.model != model or record.id <= 0 for record in records):
        raise OdooGatewayError("invalid_request")
    record_ids = tuple(record.id for record in records)
    if len(record_ids) != len(set(record_ids)):
        raise OdooGatewayError("invalid_request")
    return model, record_ids


def _field_names(fields: object) -> tuple[str, ...]:
    if not isinstance(fields, list) or not 1 <= len(fields) <= MAX_FIELDS:
        raise OdooGatewayError("invalid_request")
    if any(not isinstance(name, str) or not _FIELD_PATTERN.fullmatch(name) for name in fields):
        raise OdooGatewayError("invalid_request")
    parsed = tuple(fields)
    if len(parsed) != len(set(parsed)):
        raise OdooGatewayError("invalid_request")
    return parsed


def _validate_metadata_description(value: dict[str, JsonValue]) -> None:
    if not set(value).issubset(_METADATA_ATTRIBUTES):
        raise ValueError("invalid metadata description")
    for key, item in value.items():
        if key in {"type", "string", "relation"}:
            if item is not None and (not isinstance(item, str) or len(item) > 256):
                raise ValueError("invalid metadata description")
        elif key in {"required", "readonly"}:
            if not isinstance(item, bool):
                raise ValueError("invalid metadata description")
        elif key == "selection":
            if not isinstance(item, list) or len(item) > 64:
                raise ValueError("invalid metadata description")
            for option in item:
                if (
                    not isinstance(option, list)
                    or len(option) != 2
                    or not all(isinstance(part, str) and len(part) <= 256 for part in option)
                ):
                    raise ValueError("invalid metadata description")


def _status_error(status: int) -> str:
    if 300 <= status < 400:
        return "redirect_rejected"
    return {
        401: "machine_auth_rejected",
        403: "delegation_rejected",
        404: "endpoint_unavailable",
        429: "rate_limited",
    }.get(status, "upstream_unavailable" if status >= 500 else "upstream_rejected")
