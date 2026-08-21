"""Bounded delegated metadata and exact-record ORM reads."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterator, Sequence
from contextlib import AbstractContextManager, contextmanager
from datetime import UTC, date, datetime
from typing import Final, Protocol
from uuid import UUID

from odoo import api
from odoo.exceptions import AccessError, MissingError, ValidationError
from odoo.modules.registry import Registry

from ..security import DelegationCodec, DelegationPayload, DelegationTokenError

MAX_REQUEST_RECORDS: Final = 8
MAX_REQUEST_FIELDS: Final = 64
MAX_METADATA_FIELDS: Final = 64
MAX_RESPONSE_BYTES: Final = 128 * 1024
MAX_VALUE_STRING_LENGTH: Final = 32 * 1024
MAX_VALUE_COLLECTION_ITEMS: Final = 1_000
METADATA_ATTRIBUTES: Final = (
    "type",
    "string",
    "required",
    "readonly",
    "relation",
    "selection",
)
METADATA_FIELD_PRIORITY: Final = (
    "id",
    "display_name",
    "name",
    "state",
    "company_id",
)
ALLOWED_READ_FIELD_TYPES: Final = frozenset(
    {
        "boolean",
        "char",
        "date",
        "datetime",
        "float",
        "html",
        "integer",
        "json",
        "many2many",
        "many2one",
        "monetary",
        "one2many",
        "reference",
        "selection",
        "text",
    }
)

_MODEL_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]{0,127}$")
_FIELD_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")

JsonValue = str | int | float | bool | list["JsonValue"] | dict[str, "JsonValue"] | None


class OrmToolError(RuntimeError):
    """Sanitized tool failure safe for the service boundary."""

    def __init__(self, code: str, status: int) -> None:
        super().__init__(code)
        self.code = code
        self.status = status


class EnvironmentProvider(Protocol):
    def __call__(
        self, claims: DelegationPayload
    ) -> AbstractContextManager[object]: ...


class ReplayGuard(Protocol):
    def __call__(self, claims: DelegationPayload, scope: str) -> None: ...


class DelegatedOrmToolExecutor:
    """Validate delegation and execute only the two M2 read capabilities."""

    def __init__(
        self,
        *,
        codec: DelegationCodec,
        environment_provider: EnvironmentProvider | None = None,
        replay_guard: ReplayGuard | None = None,
        observed_at: Callable[[], datetime] | None = None,
    ) -> None:
        self._codec = codec
        self._environment_provider = environment_provider or _runtime_environment
        self._replay_guard = replay_guard or _runtime_replay_guard
        self._observed_at = observed_at or _utc_now

    def get_model_metadata(
        self,
        *,
        delegation_token: str,
        turn_id: object,
        model: object,
    ) -> dict[str, JsonValue]:
        parsed_turn = _turn_id(turn_id)
        parsed_model = _model_name(model)
        claims = self._authorize(
            delegation_token,
            turn_id=parsed_turn,
            scope="fields_get",
            model=parsed_model,
        )
        self._replay_guard(claims, "fields_get")
        try:
            with self._environment_provider(claims) as env:
                model_set = env[parsed_model]
                model_set.browse().check_access("read")
                descriptions = model_set.fields_get(
                    attributes=list(METADATA_ATTRIBUTES)
                )
        except (AccessError, MissingError, ValidationError):
            raise OrmToolError("access_denied", 403) from None
        except KeyError:
            raise OrmToolError("access_denied", 403) from None

        field_limit = min(claims.max_fields, MAX_METADATA_FIELDS)
        names = _prioritized_field_names(descriptions)[:field_limit]
        fields_payload = {
            name: _normalize_field_definition(descriptions[name]) for name in names
        }
        result: dict[str, JsonValue] = {
            "captured_at": _iso_datetime(self._observed_at()),
            "fields": fields_payload,
            "model": parsed_model,
            "ok": True,
        }
        _check_response_size(result)
        return result

    def read_records(
        self,
        *,
        delegation_token: str,
        turn_id: object,
        model: object,
        record_ids: object,
        fields: object,
    ) -> dict[str, JsonValue]:
        parsed_turn = _turn_id(turn_id)
        parsed_model = _model_name(model)
        parsed_ids = _record_ids(record_ids)
        parsed_fields = _field_names(fields)
        claims = self._authorize(
            delegation_token,
            turn_id=parsed_turn,
            scope="read_records",
            model=parsed_model,
        )
        if (
            len(parsed_ids) > claims.max_records
            or not set(parsed_ids).issubset(claims.record_ids)
        ):
            raise OrmToolError("scope_denied", 403)
        if len(parsed_fields) > claims.max_fields:
            raise OrmToolError("limit_exceeded", 413)
        self._replay_guard(claims, "read_records")

        try:
            with self._environment_provider(claims) as env:
                model_set = env[parsed_model]
                unknown = set(parsed_fields) - set(model_set._fields)
                if unknown:
                    raise OrmToolError("invalid_fields", 400)
                model_set.check_field_access_rights("read", list(parsed_fields))
                unsupported = {
                    name
                    for name in parsed_fields
                    if model_set._fields[name].type not in ALLOWED_READ_FIELD_TYPES
                }
                if unsupported:
                    raise OrmToolError("unsupported_fields", 400)
                records = model_set.browse(parsed_ids)
                records.check_access("read")
                rows = records.read(list(parsed_fields), load=None)
        except OrmToolError:
            raise
        except (AccessError, MissingError, ValidationError):
            raise OrmToolError("access_denied", 403) from None
        except KeyError:
            raise OrmToolError("access_denied", 403) from None
        except ValueError:
            raise OrmToolError("invalid_fields", 400) from None

        rows_by_id = {row.get("id"): row for row in rows}
        if set(rows_by_id) != set(parsed_ids):
            raise OrmToolError("access_denied", 403)
        records_payload: list[JsonValue] = []
        for record_id in parsed_ids:
            row = rows_by_id[record_id]
            normalized_fields = {
                name: _normalize_value(row.get(name)) for name in parsed_fields
            }
            display_name = normalized_fields.get("display_name")
            records_payload.append(
                {
                    "display_name": (
                        display_name if isinstance(display_name, str) else None
                    ),
                    "fields": normalized_fields,
                    "id": record_id,
                }
            )
        result = {
            "captured_at": _iso_datetime(self._observed_at()),
            "model": parsed_model,
            "ok": True,
            "records": records_payload,
        }
        _check_response_size(result)
        return result

    def _authorize(
        self,
        token: str,
        *,
        turn_id: UUID,
        scope: str,
        model: str,
    ) -> DelegationPayload:
        try:
            claims = self._codec.decode(token)
        except DelegationTokenError:
            raise OrmToolError("delegation_rejected", 403) from None
        if claims.turn_id != turn_id or model != claims.model or scope not in claims.scopes:
            raise OrmToolError("scope_denied", 403)
        return claims


@contextmanager
def _runtime_environment(claims: DelegationPayload) -> Iterator[object]:
    """Open an Odoo Environment as the delegated user without superuser mode."""

    context: dict[str, object] = {
        "allowed_company_ids": list(claims.allowed_company_ids)
    }
    if claims.lang is not None:
        context["lang"] = claims.lang
    try:
        database_registry = Registry(claims.database)
        with database_registry.cursor() as cursor:
            env = api.Environment(cursor, claims.uid, context, su=False)
            if env.su or env.cr.dbname != claims.database:
                raise OrmToolError("delegation_rejected", 403)
            # Accessing both properties invokes Odoo 18's company authorization checks.
            if (
                env.company.id != claims.company_id
                or tuple(env.companies.ids) != claims.allowed_company_ids
            ):
                raise OrmToolError("delegation_rejected", 403)
            yield env
    except OrmToolError:
        raise
    except (AccessError, MissingError, ValidationError):
        raise OrmToolError("delegation_rejected", 403) from None
    except Exception:  # noqa: BLE001 - sanitize the Odoo registry boundary
        raise OrmToolError("service_unavailable", 503) from None


def _runtime_replay_guard(claims: DelegationPayload, scope: str) -> None:
    """Consume one scope in Odoo before any delegated business-data access."""

    try:
        with _runtime_environment(claims) as env:
            consumed = env["odoo.ai.delegation.use"]._consume(
                jti=claims.jti,
                scope=scope,
                expires_at=claims.expires_at,
            )
    except OrmToolError:
        raise
    except (AccessError, MissingError, ValidationError):
        raise OrmToolError("delegation_rejected", 403) from None
    except Exception:  # noqa: BLE001 - sanitize the technical ledger boundary
        raise OrmToolError("service_unavailable", 503) from None
    if consumed is not True:
        raise OrmToolError("delegation_replayed", 403)


def _turn_id(value: object) -> UUID:
    try:
        parsed = UUID(str(value))
    except (TypeError, ValueError, AttributeError):
        raise OrmToolError("invalid_request", 400) from None
    if str(parsed) != str(value):
        raise OrmToolError("invalid_request", 400)
    return parsed


def _model_name(value: object) -> str:
    if not isinstance(value, str) or not _MODEL_PATTERN.fullmatch(value):
        raise OrmToolError("invalid_request", 400)
    return value


def _record_ids(value: object) -> tuple[int, ...]:
    if not isinstance(value, list) or not 1 <= len(value) <= MAX_REQUEST_RECORDS:
        raise OrmToolError("limit_exceeded", 413)
    if any(type(item) is not int or item <= 0 for item in value):
        raise OrmToolError("invalid_request", 400)
    parsed = tuple(value)
    if len(parsed) != len(set(parsed)):
        raise OrmToolError("invalid_request", 400)
    return parsed


def _field_names(value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or not 1 <= len(value) <= MAX_REQUEST_FIELDS:
        raise OrmToolError("limit_exceeded", 413)
    if any(not isinstance(item, str) or not _FIELD_PATTERN.fullmatch(item) for item in value):
        raise OrmToolError("invalid_request", 400)
    parsed = tuple(value)
    if len(parsed) != len(set(parsed)):
        raise OrmToolError("invalid_request", 400)
    return parsed


def _prioritized_field_names(descriptions: object) -> list[str]:
    if not isinstance(descriptions, dict) or not all(
        isinstance(name, str) and isinstance(value, dict)
        for name, value in descriptions.items()
    ):
        raise OrmToolError("invalid_metadata", 500)
    priority = [name for name in METADATA_FIELD_PRIORITY if name in descriptions]
    return priority + sorted(set(descriptions) - set(priority))


def _normalize_field_definition(value: object) -> JsonValue:
    if not isinstance(value, dict):
        raise OrmToolError("invalid_metadata", 500)
    normalized: dict[str, JsonValue] = {}
    for attribute in METADATA_ATTRIBUTES:
        if attribute not in value:
            continue
        item = value[attribute]
        if attribute in {"type", "string", "relation"}:
            if item is False or item is None:
                normalized[attribute] = None
            elif isinstance(item, str) and len(item) <= 256:
                normalized[attribute] = item
            else:
                raise OrmToolError("invalid_metadata", 500)
        elif attribute in {"required", "readonly"}:
            if not isinstance(item, bool):
                raise OrmToolError("invalid_metadata", 500)
            normalized[attribute] = item
        elif attribute == "selection":
            if item is None or item is False:
                continue
            if not isinstance(item, Sequence) or isinstance(item, (str, bytes)):
                raise OrmToolError("invalid_metadata", 500)
            if len(item) > 64:
                raise OrmToolError("limit_exceeded", 413)
            selection: list[JsonValue] = []
            for option in item:
                if (
                    not isinstance(option, (list, tuple))
                    or len(option) != 2
                    or not all(isinstance(part, str) and len(part) <= 256 for part in option)
                ):
                    raise OrmToolError("invalid_metadata", 500)
                selection.append([option[0], option[1]])
            normalized[attribute] = selection
    return normalized


def _normalize_value(value: object) -> JsonValue:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        if len(value) > MAX_VALUE_STRING_LENGTH:
            raise OrmToolError("response_too_large", 413)
        return value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, (list, tuple)):
        if len(value) > MAX_VALUE_COLLECTION_ITEMS:
            raise OrmToolError("response_too_large", 413)
        return [_normalize_value(item) for item in value]
    if isinstance(value, dict):
        if len(value) > MAX_VALUE_COLLECTION_ITEMS or not all(
            isinstance(key, str) for key in value
        ):
            raise OrmToolError("response_too_large", 413)
        return {key: _normalize_value(item) for key, item in value.items()}
    raise OrmToolError("unsupported_value", 400)


def _check_response_size(payload: dict[str, JsonValue]) -> None:
    try:
        serialized = json.dumps(
            payload,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError):
        raise OrmToolError("serialization_failed", 500) from None
    if len(serialized) > MAX_RESPONSE_BYTES:
        raise OrmToolError("response_too_large", 413)


def _iso_datetime(value: datetime) -> str:
    if value.tzinfo is None:
        raise OrmToolError("clock_unavailable", 500)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _utc_now() -> datetime:
    return datetime.now(UTC)
