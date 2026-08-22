"""Build a bounded effective schema from delegated Odoo runtime metadata."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Final, cast
from uuid import uuid4

from odoo_ai.contracts import (
    EffectiveFieldSchema,
    EffectiveModelSchema,
    EffectiveSelectionOption,
    Evidence,
    EvidenceKind,
    EvidenceSensitivity,
    EvidenceStatus,
)
from odoo_ai.ports.odoo import ModelMetadataGateway

type JsonValue = str | int | float | bool | list[JsonValue] | dict[str, JsonValue] | None

MAX_EFFECTIVE_FIELDS: Final = 64
MAX_EFFECTIVE_SCHEMA_BYTES: Final = 64 * 1024
MAX_SELECTION_OPTIONS: Final = 64
DEFAULT_POLICY_REVISION: Final = "m5-query-read-v1"

_MODEL_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]{0,127}$")
_FIELD_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")
_RELATIONAL_TYPES = frozenset({"many2many", "many2one", "one2many"})
_SUPPORTED_FIELD_TYPES = frozenset(
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
_SEARCHABLE_TYPES = _SUPPORTED_FIELD_TYPES
_SORTABLE_TYPES = frozenset(
    {
        "boolean",
        "char",
        "date",
        "datetime",
        "float",
        "integer",
        "many2one",
        "monetary",
        "selection",
    }
)
_GROUPABLE_TYPES = frozenset(
    {"boolean", "char", "date", "datetime", "integer", "many2one", "selection"}
)
_RAW_FIELD_KEYS = frozenset(
    {
        "groupable",
        "readonly",
        "relation",
        "required",
        "searchable",
        "selection",
        "sortable",
        "string",
        "type",
    }
)
_REQUIRED_RAW_FIELD_KEYS = frozenset(
    {"groupable", "readonly", "required", "searchable", "sortable", "type"}
)


class EffectiveSchemaError(RuntimeError):
    """Sanitized failure while deriving an effective runtime schema."""

    def __init__(self, code: str, status_code: int = 502) -> None:
        super().__init__(code)
        self.code = code
        self.status_code = status_code


@dataclass(frozen=True, slots=True)
class EffectiveSchemaPolicy:
    """Small fail-closed policy applied after Odoo reports runtime capabilities."""

    revision: str = DEFAULT_POLICY_REVISION
    max_fields: int = MAX_EFFECTIVE_FIELDS
    max_bytes: int = MAX_EFFECTIVE_SCHEMA_BYTES
    allowed_field_types: frozenset[str] = _SUPPORTED_FIELD_TYPES
    searchable_field_types: frozenset[str] = _SEARCHABLE_TYPES
    sortable_field_types: frozenset[str] = _SORTABLE_TYPES
    groupable_field_types: frozenset[str] = _GROUPABLE_TYPES

    def __post_init__(self) -> None:
        if (
            not isinstance(self.revision, str)
            or not 1 <= len(self.revision) <= 128
            or type(self.max_fields) is not int
            or not 1 <= self.max_fields <= MAX_EFFECTIVE_FIELDS
            or type(self.max_bytes) is not int
            or not 1 <= self.max_bytes <= MAX_EFFECTIVE_SCHEMA_BYTES
        ):
            raise EffectiveSchemaError("invalid_schema_policy", 500)
        capability_types = (
            self.searchable_field_types | self.sortable_field_types | self.groupable_field_types
        )
        if (
            not self.allowed_field_types
            or not capability_types.issubset(self.allowed_field_types)
            or any(not _FIELD_PATTERN.fullmatch(item) for item in self.allowed_field_types)
        ):
            raise EffectiveSchemaError("invalid_schema_policy", 500)


@dataclass(frozen=True, slots=True)
class EffectiveSchemaResult:
    """Effective schema plus the checked metadata evidence that cites it."""

    schema: EffectiveModelSchema
    evidence: Evidence


class EffectiveSchemaService:
    """Derive one deterministic schema from a gateway already bound to a turn."""

    def __init__(
        self,
        gateway: ModelMetadataGateway,
        *,
        policy: EffectiveSchemaPolicy | None = None,
    ) -> None:
        self._gateway = gateway
        self._policy = policy or EffectiveSchemaPolicy()

    async def get(self, *, model: str, captured_for_user: int) -> EffectiveSchemaResult:
        if not isinstance(model, str) or not _MODEL_PATTERN.fullmatch(model):
            raise EffectiveSchemaError("invalid_model", 422)
        if type(captured_for_user) is not int or captured_for_user <= 0:
            raise EffectiveSchemaError("invalid_user_context", 422)

        metadata = await self._gateway.get_model_metadata(model)
        raw_fields, label, captured_at = _validate_metadata_evidence(
            metadata,
            model=model,
            max_fields=self._policy.max_fields,
        )
        fields = {
            name: _effective_field(name, raw_fields[name], self._policy)
            for name in sorted(raw_fields)
        }
        canonical_body = {
            "captured_for_user": captured_for_user,
            "fields": {name: field.model_dump(mode="json") for name, field in fields.items()},
            "label": label,
            "model": model,
            "policy_revision": self._policy.revision,
            "source": "runtime",
        }
        digest = hashlib.sha256(_canonical_bytes(canonical_body)).hexdigest()
        fingerprint = f"sha256:{digest}"
        try:
            schema = EffectiveModelSchema(
                schema_id=fingerprint,
                model=model,
                label=label,
                revision=fingerprint,
                fields=fields,
                captured_for_user=captured_for_user,
                policy_revision=self._policy.revision,
                captured_at=captured_at,
            )
        except ValueError:
            raise EffectiveSchemaError("invalid_metadata") from None
        serialized = _canonical_bytes(schema.model_dump(mode="json"))
        if len(serialized) > self._policy.max_bytes:
            raise EffectiveSchemaError("schema_too_large", 413)

        evidence = Evidence(
            evidence_id=uuid4(),
            kind=EvidenceKind.METADATA,
            status=EvidenceStatus.CHECKED,
            title=f"Effective Odoo schema: {model}",
            summary="Runtime fields were checked under the delegated user and bounded by policy.",
            payload=cast(dict[str, JsonValue], schema.model_dump(mode="json")),
            pointer={
                "model": model,
                "provider": "effective_schema",
                "schema_id": schema.schema_id,
            },
            observed_at=schema.captured_at,
            sensitivity=EvidenceSensitivity.TECHNICAL,
            fingerprint=fingerprint,
        )
        return EffectiveSchemaResult(schema=schema, evidence=evidence)


def _validate_metadata_evidence(
    metadata: Evidence,
    *,
    model: str,
    max_fields: int,
) -> tuple[dict[str, dict[str, JsonValue]], str | None, datetime]:
    if (
        metadata.kind is not EvidenceKind.METADATA
        or metadata.status is not EvidenceStatus.CHECKED
        or metadata.observed_at is None
        or metadata.observed_at.utcoffset() is None
        or set(metadata.payload) - {"fields", "label", "model"}
        or metadata.payload.get("model") != model
        or not isinstance(metadata.pointer, dict)
        or metadata.pointer.get("model") != model
    ):
        raise EffectiveSchemaError("invalid_metadata")
    label = metadata.payload.get("label")
    if label is not None and (not isinstance(label, str) or not label or len(label) > 256):
        raise EffectiveSchemaError("invalid_metadata")
    raw_fields = metadata.payload.get("fields")
    if (
        not isinstance(raw_fields, dict)
        or not 1 <= len(raw_fields) <= max_fields
        or any(
            not isinstance(name, str)
            or not _FIELD_PATTERN.fullmatch(name)
            or not isinstance(description, dict)
            for name, description in raw_fields.items()
        )
    ):
        raise EffectiveSchemaError("invalid_metadata")
    return (
        cast(dict[str, dict[str, JsonValue]], raw_fields),
        label,
        metadata.observed_at,
    )


def _effective_field(
    name: str,
    raw: dict[str, JsonValue],
    policy: EffectiveSchemaPolicy,
) -> EffectiveFieldSchema:
    if set(raw) - _RAW_FIELD_KEYS or not _REQUIRED_RAW_FIELD_KEYS.issubset(raw):
        raise EffectiveSchemaError("invalid_metadata")
    field_type = raw.get("type")
    if not isinstance(field_type, str) or field_type not in policy.allowed_field_types:
        raise EffectiveSchemaError("unsupported_metadata")
    label = raw.get("string")
    if label is not None and (not isinstance(label, str) or not label or len(label) > 256):
        raise EffectiveSchemaError("invalid_metadata")
    booleans = {
        key: raw.get(key) for key in ("required", "readonly", "searchable", "sortable", "groupable")
    }
    if any(not isinstance(value, bool) for value in booleans.values()):
        raise EffectiveSchemaError("invalid_metadata")

    relation = raw.get("relation")
    if field_type in _RELATIONAL_TYPES:
        if not isinstance(relation, str) or not _MODEL_PATTERN.fullmatch(relation):
            raise EffectiveSchemaError("invalid_metadata")
    elif relation is not None:
        raise EffectiveSchemaError("invalid_metadata")

    selection = _selection(raw.get("selection"), field_type=field_type)
    try:
        return EffectiveFieldSchema(
            name=name,
            label=label,
            field_type=field_type,
            relation=relation,
            required=cast(bool, booleans["required"]),
            readonly=cast(bool, booleans["readonly"]),
            searchable=cast(bool, booleans["searchable"])
            and field_type in policy.searchable_field_types,
            sortable=cast(bool, booleans["sortable"]) and field_type in policy.sortable_field_types,
            groupable=cast(bool, booleans["groupable"])
            and field_type in policy.groupable_field_types,
            selection=selection,
        )
    except ValueError:
        raise EffectiveSchemaError("invalid_metadata") from None


def _selection(
    value: JsonValue | None,
    *,
    field_type: str,
) -> tuple[EffectiveSelectionOption, ...] | None:
    if field_type != "selection":
        if value is not None:
            raise EffectiveSchemaError("invalid_metadata")
        return None
    if not isinstance(value, list) or not 1 <= len(value) <= MAX_SELECTION_OPTIONS:
        raise EffectiveSchemaError("invalid_metadata")
    options: list[EffectiveSelectionOption] = []
    seen: set[str] = set()
    for item in value:
        option_value = item[0] if isinstance(item, list) and item else None
        option_label = item[1] if isinstance(item, list) and len(item) > 1 else None
        if (
            not isinstance(item, list)
            or len(item) != 2
            or not isinstance(option_value, str)
            or not isinstance(option_label, str)
            or not 1 <= len(option_value) <= 256
            or not 1 <= len(option_label) <= 256
            or option_value in seen
        ):
            raise EffectiveSchemaError("invalid_metadata")
        seen.add(option_value)
        options.append(EffectiveSelectionOption(value=option_value, label=option_label))
    return tuple(options)


def _canonical_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError):
        raise EffectiveSchemaError("invalid_metadata") from None
