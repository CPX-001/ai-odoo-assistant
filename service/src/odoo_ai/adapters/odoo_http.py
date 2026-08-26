"""Machine-authenticated Odoo inventory transport for residual Source scanning."""

from __future__ import annotations

import asyncio
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from http.client import HTTPConnection, HTTPException, HTTPResponse, HTTPSConnection
from typing import Final, Literal
from urllib.parse import urlsplit, urlunsplit

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, ValidationError, field_validator

from odoo_ai.contracts import InstanceInventory
from odoo_ai.ports import OdooGatewayError
from odoo_ai.security import SHARED_SECRET_HEADER, SharedSecretError, load_shared_secret

ODOO_BASE_URL_ENV: Final = "ODOO_AI_ODOO_BASE_URL"
INVENTORY_ROUTE: Final = "/odoo_ai/internal/v1/instance-inventory"
DEFAULT_TIMEOUT_SECONDS: Final = 2.0
MAX_RESPONSE_BYTES: Final = 128 * 1024
SecretLoader = Callable[[], str]


@dataclass(frozen=True, slots=True)
class OdooGatewaySettings:
    """Validated routing and transport limits for the residual inventory callback."""

    base_url: str
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
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
        cls,
        environ: Mapping[str, str] | None = None,
    ) -> OdooGatewaySettings:
        source = os.environ if environ is None else environ
        raw_url = source.get(ODOO_BASE_URL_ENV, "")
        if not raw_url:
            raise OdooGatewayError("gateway_unconfigured")
        return cls(base_url=raw_url)


class OdooGatewayFactory:
    """Bind residual inventory transport configuration and machine credentials."""

    __slots__ = ("_secret_loader", "_settings")

    def __init__(
        self,
        settings: OdooGatewaySettings,
        *,
        secret_loader: SecretLoader = load_shared_secret,
    ) -> None:
        self._settings = settings
        self._secret_loader = secret_loader

    def for_instance(self) -> HttpOdooInstanceGateway:
        try:
            machine_secret = self._secret_loader()
        except SharedSecretError:
            raise OdooGatewayError("machine_auth_unavailable") from None
        _validate_header_secret(machine_secret, maximum=4096)
        return HttpOdooInstanceGateway(
            settings=self._settings,
            machine_secret=machine_secret,
        )


class HttpOdooInstanceGateway:
    """Read bounded technical deployment metadata without business-record authority."""

    __slots__ = ("_machine_secret", "_settings")

    def __init__(self, *, settings: OdooGatewaySettings, machine_secret: str) -> None:
        if not isinstance(settings, OdooGatewaySettings):
            raise OdooGatewayError("invalid_configuration")
        _validate_header_secret(machine_secret, maximum=4096)
        self._settings = settings
        self._machine_secret = machine_secret

    def __repr__(self) -> str:
        return (
            f"{type(self).__name__}(base_url={self._settings.base_url!r}, "
            "credentials=<redacted>)"
        )

    async def get_instance_inventory(self) -> InstanceInventory:
        raw = await asyncio.to_thread(self._post_json)
        try:
            response = _InventoryResponse.model_validate_json(raw)
        except ValidationError:
            raise OdooGatewayError("malformed_response") from None
        return InstanceInventory(
            database=response.database,
            server_version=response.server_version,
            installed_modules=tuple(response.installed_modules),
            addons_roots=tuple(response.addons_roots),
            captured_at=response.captured_at,
        )

    def _post_json(self) -> bytes:
        connection = _connection(self._settings)
        try:
            connection.request(
                "POST",
                INVENTORY_ROUTE,
                body=b"{}",
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    SHARED_SECRET_HEADER: self._machine_secret,
                },
            )
            return _read_response(connection.getresponse(), self._settings)
        except OdooGatewayError:
            raise
        except TimeoutError:
            raise OdooGatewayError("upstream_timeout") from None
        except (HTTPException, OSError):
            raise OdooGatewayError("upstream_unavailable") from None
        finally:
            connection.close()


class _InventoryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    addons_roots: list[str] = Field(max_length=128)
    captured_at: AwareDatetime
    database: str = Field(min_length=1, max_length=128)
    installed_modules: list[str] = Field(max_length=4096)
    ok: Literal[True]
    server_version: str = Field(min_length=1, max_length=64)

    @field_validator("addons_roots", "installed_modules")
    @classmethod
    def validate_unique_text(cls, value: list[str]) -> list[str]:
        if any(not item or item != item.strip() or len(item) > 4096 for item in value):
            raise ValueError("invalid instance inventory")
        if len(value) != len(set(value)):
            raise ValueError("invalid instance inventory")
        return value


def _connection(settings: OdooGatewaySettings):
    connection_type = HTTPSConnection if settings._scheme == "https" else HTTPConnection
    return connection_type(
        settings._host,
        settings._port,
        timeout=float(settings.timeout_seconds),
    )


def _read_response(response: HTTPResponse, settings: OdooGatewaySettings) -> bytes:
    if response.status != 200:
        raise OdooGatewayError(_status_error(response.status))
    content_type = response.getheader("Content-Type", "").partition(";")[0].strip()
    if content_type != "application/json":
        raise OdooGatewayError("malformed_response")
    body = response.read(settings.max_response_bytes + 1)
    if len(body) > settings.max_response_bytes:
        raise OdooGatewayError("response_too_large")
    if not body:
        raise OdooGatewayError("malformed_response")
    return body


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
    normalized = urlunsplit(
        (parsed.scheme, f"{display_host}{display_port}", "", "", "")
    )
    return parsed.scheme, host, effective_port, normalized


def _validate_header_secret(value: object, *, maximum: int) -> None:
    if (
        not isinstance(value, str)
        or not 1 <= len(value) <= maximum
        or any(ord(character) < 33 or ord(character) > 126 for character in value)
    ):
        raise OdooGatewayError("machine_auth_unavailable")


def _status_error(status: int) -> str:
    if 300 <= status < 400:
        return "redirect_rejected"
    return {
        401: "machine_auth_rejected",
        403: "machine_auth_rejected",
        404: "endpoint_unavailable",
        429: "rate_limited",
    }.get(status, "upstream_unavailable" if status >= 500 else "upstream_rejected")
