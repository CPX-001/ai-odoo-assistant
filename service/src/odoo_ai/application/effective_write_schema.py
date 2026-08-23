"""Derive bounded write eligibility from live Odoo metadata and ActionPolicy."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Final, cast
from uuid import uuid4

from odoo_ai.application.action_policy import ActionPolicy
from odoo_ai.contracts import (
    ActionValueKind,
    EffectiveWriteFieldSchema,
    EffectiveWriteSchema,
    Evidence,
    EvidenceKind,
    EvidenceSensitivity,
    EvidenceStatus,
)
from odoo_ai.ports.odoo import OdooActionPreviewGateway

type JsonValue = str | int | float | bool | list[JsonValue] | dict[str, JsonValue] | None

MAX_EFFECTIVE_WRITE_FIELDS: Final = 64
MAX_EFFECTIVE_WRITE_SCHEMA_BYTES: Final = 48 * 1024

_MODEL_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]{0,127}$")
_FIELD_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")
_SUPPORTED_TYPES = {
    "boolean": ActionValueKind.BOOLEAN,
    "char": ActionValueKind.TEXT,
    "date": ActionValueKind.DATE,
    "datetime": ActionValueKind.DATETIME,
    "float": ActionValueKind.DECIMAL,
    "integer": ActionValueKind.INTEGER,
    "many2one": ActionValueKind.MANY2ONE,
    "monetary": ActionValueKind.DECIMAL,
    "selection": ActionValueKind.SELECTION,
    "text": ActionValueKind.TEXT,
}
_RAW_KEYS = frozenset(
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


class EffectiveWriteSchemaError(RuntimeError):
    """Sanitized write-schema derivation failure."""

    def __init__(self, code: str, status_code: int = 502) -> None:
        super().__init__(code)
        self.code = code
        self.status_code = status_code


@dataclass(frozen=True, slots=True)
class EffectiveWriteSchemaResult:
    schema: EffectiveWriteSchema
    evidence: Evidence


class EffectiveWriteSchemaService:
    """Build a non-authorizing schema from a p1-bound Odoo gateway."""

    def __init__(
        self,
        gateway: OdooActionPreviewGateway,
        *,
        policy: ActionPolicy | None = None,
    ) -> None:
        self._gateway = gateway
        self._policy = policy or ActionPolicy()

    async def get(
        self,
        *,
        model: str,
        instance_id: str,
        database: str,
        captured_for_user: int,
        company_id: int,
        allowed_company_ids: tuple[int, ...],
    ) -> EffectiveWriteSchemaResult:
        if not isinstance(model, str) or _MODEL_PATTERN.fullmatch(model) is None:
            raise EffectiveWriteSchemaError("invalid_model", 422)
        if type(captured_for_user) is not int or captured_for_user <= 0:
            raise EffectiveWriteSchemaError("invalid_user_context", 422)
        if (
            not isinstance(instance_id, str)
            or not 1 <= len(instance_id) <= 255
            or instance_id != instance_id.strip()
            or not isinstance(database, str)
            or not 1 <= len(database) <= 128
            or database != database.strip()
            or type(company_id) is not int
            or company_id <= 0
            or not isinstance(allowed_company_ids, tuple)
            or not 1 <= len(allowed_company_ids) <= 16
            or any(type(item) is not int or item <= 0 for item in allowed_company_ids)
            or len(allowed_company_ids) != len(set(allowed_company_ids))
            or allowed_company_ids != tuple(sorted(allowed_company_ids))
            or company_id not in allowed_company_ids
        ):
            raise EffectiveWriteSchemaError("invalid_user_context", 422)

        metadata = await self._gateway.get_write_model_metadata(model)
        raw_fields, label, write_access, create_access, captured_at = _validate_metadata(
            metadata, model=model
        )
        fields: dict[str, EffectiveWriteFieldSchema] = {}
        create_fields: dict[str, EffectiveWriteFieldSchema] = {}
        if (write_access or create_access) and self._policy.permits_model(model):
            for name in sorted(raw_fields):
                field = _effective_write_field(name, raw_fields[name], self._policy)
                if field is not None:
                    if write_access:
                        fields[name] = field
                    if create_access:
                        create_fields[name] = field

        canonical_body = {
            "allowed_company_ids": list(allowed_company_ids),
            "captured_for_user": captured_for_user,
            "company_id": company_id,
            "create_access": create_access,
            "create_fields": {
                name: field.model_dump(mode="json") for name, field in create_fields.items()
            },
            "database": database,
            "fields": {name: field.model_dump(mode="json") for name, field in fields.items()},
            "instance_id": instance_id,
            "label": label,
            "model": model,
            "policy_revision": self._policy.revision,
            "source": "runtime",
            "write_access": write_access,
        }
        digest = hashlib.sha256(_canonical_bytes(canonical_body)).hexdigest()
        schema_id = f"action-schema:v1:sha256:{digest}"
        try:
            schema = EffectiveWriteSchema(
                schema_id=schema_id,
                instance_id=instance_id,
                database=database,
                model=model,
                label=label,
                write_access=write_access,
                fields=fields,
                create_access=create_access,
                create_fields=create_fields,
                captured_for_user=captured_for_user,
                company_id=company_id,
                allowed_company_ids=allowed_company_ids,
                policy_revision=self._policy.revision,
                captured_at=captured_at,
            )
        except ValueError:
            raise EffectiveWriteSchemaError("invalid_metadata") from None
        if len(_canonical_bytes(schema.model_dump(mode="json"))) > MAX_EFFECTIVE_WRITE_SCHEMA_BYTES:
            raise EffectiveWriteSchemaError("schema_too_large", 413)

        evidence = Evidence(
            evidence_id=uuid4(),
            kind=EvidenceKind.METADATA,
            status=EvidenceStatus.CHECKED,
            title=f"Effective Odoo write schema: {model}",
            summary=(
                "Write and create eligibility were checked under the delegated user "
                "and bounded by policy."
            ),
            payload=cast(dict[str, JsonValue], schema.model_dump(mode="json")),
            pointer={
                "model": model,
                "provider": "effective_write_schema",
                "schema_id": schema.schema_id,
            },
            observed_at=schema.captured_at,
            sensitivity=EvidenceSensitivity.TECHNICAL,
            fingerprint=schema_id,
        )
        return EffectiveWriteSchemaResult(schema=schema, evidence=evidence)


def _validate_metadata(
    metadata: Evidence, *, model: str
) -> tuple[dict[str, dict[str, JsonValue]], str | None, bool, bool, datetime]:
    if (
        metadata.kind is not EvidenceKind.METADATA
        or metadata.status is not EvidenceStatus.CHECKED
        or metadata.observed_at is None
        or metadata.observed_at.utcoffset() is None
        or set(metadata.payload)
        not in (
            {"fields", "label", "model", "write_access"},
            {"create_access", "fields", "label", "model", "write_access"},
        )
        or metadata.payload.get("model") != model
        or not isinstance(metadata.pointer, dict)
        or metadata.pointer.get("model") != model
    ):
        raise EffectiveWriteSchemaError("invalid_metadata")
    label = metadata.payload.get("label")
    write_access = metadata.payload.get("write_access")
    create_access = metadata.payload.get("create_access", False)
    raw_fields = metadata.payload.get("fields")
    if (
        (label is not None and (not isinstance(label, str) or not 1 <= len(label) <= 256))
        or not isinstance(write_access, bool)
        or not isinstance(create_access, bool)
        or not isinstance(raw_fields, dict)
        or len(raw_fields) > MAX_EFFECTIVE_WRITE_FIELDS
        or any(
            not isinstance(name, str)
            or _FIELD_PATTERN.fullmatch(name) is None
            or not isinstance(description, dict)
            for name, description in raw_fields.items()
        )
    ):
        raise EffectiveWriteSchemaError("invalid_metadata")
    return (
        cast(dict[str, dict[str, JsonValue]], raw_fields),
        label,
        write_access,
        create_access,
        metadata.observed_at,
    )


def _effective_write_field(
    name: str, raw: dict[str, JsonValue], policy: ActionPolicy
) -> EffectiveWriteFieldSchema | None:
    if set(raw) - _RAW_KEYS:
        raise EffectiveWriteSchemaError("invalid_metadata")
    field_type = raw.get("type")
    readonly = raw.get("readonly")
    required = raw.get("required")
    if (
        not isinstance(field_type, str)
        or not isinstance(readonly, bool)
        or not isinstance(required, bool)
    ):
        raise EffectiveWriteSchemaError("invalid_metadata")
    value_kind = _SUPPORTED_TYPES.get(field_type)
    if readonly or value_kind is None or not policy.permits_field(name):
        return None
    if value_kind not in policy.allowed_value_kinds:
        return None
    label = raw.get("string")
    if label is not None and (not isinstance(label, str) or not 1 <= len(label) <= 256):
        raise EffectiveWriteSchemaError("invalid_metadata")
    relation = raw.get("relation")
    if value_kind is ActionValueKind.MANY2ONE:
        if not isinstance(relation, str) or _MODEL_PATTERN.fullmatch(relation) is None:
            raise EffectiveWriteSchemaError("invalid_metadata")
    elif relation is not None:
        raise EffectiveWriteSchemaError("invalid_metadata")
    selection = _selection_values(raw.get("selection"), value_kind=value_kind)
    try:
        return EffectiveWriteFieldSchema(
            name=name,
            label=label,
            field_type=field_type,
            value_kind=value_kind,
            relation=relation,
            required=required,
            selection=selection,
        )
    except ValueError:
        raise EffectiveWriteSchemaError("invalid_metadata") from None


def _selection_values(
    value: JsonValue | None, *, value_kind: ActionValueKind
) -> tuple[str, ...] | None:
    if value_kind is not ActionValueKind.SELECTION:
        if value is not None:
            raise EffectiveWriteSchemaError("invalid_metadata")
        return None
    if not isinstance(value, list) or not 1 <= len(value) <= 64:
        raise EffectiveWriteSchemaError("invalid_metadata")
    options: list[str] = []
    for item in value:
        option = item[0] if isinstance(item, list) and len(item) == 2 else None
        label = item[1] if isinstance(item, list) and len(item) == 2 else None
        if (
            not isinstance(option, str)
            or not isinstance(label, str)
            or not 1 <= len(option) <= 256
            or not 1 <= len(label) <= 256
            or option in options
        ):
            raise EffectiveWriteSchemaError("invalid_metadata")
        options.append(option)
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
        raise EffectiveWriteSchemaError("invalid_metadata") from None
