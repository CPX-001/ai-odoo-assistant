"""Strict, provider-neutral contracts for the bounded M6 ACTION pipeline."""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Annotated, Final, Literal, Self
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

ACTION_PAYLOAD_FORMAT_VERSION: Final = 1
MAX_ACTION_COMPANIES: Final = 16
MAX_ACTION_FIELDS: Final = 4
MAX_ACTION_WARNINGS: Final = 8
MAX_ACTION_VALUE_TEXT: Final = 4_000

PositiveId = Annotated[int, Field(strict=True, gt=0)]
ModelName = Annotated[str, Field(pattern=r"^[A-Za-z_][A-Za-z0-9_.]{0,127}$")]
FieldName = Annotated[str, Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")]
Revision = Annotated[str, Field(min_length=1, max_length=128)]
Fingerprint = Annotated[
    str,
    Field(pattern=r"^[a-z][a-z0-9_-]{0,31}:v[0-9]+:sha256:[0-9a-f]{64}$"),
]

_DECIMAL_PATTERN = re.compile(r"^-?(?:0|[1-9][0-9]{0,15})(?:\.[0-9]{1,6})?$")
_DATE_PATTERN = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
_DATETIME_PATTERN = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")


class ActionKind(StrEnum):
    """Closed ACTION kinds supported by the first write slice."""

    RECORD_PATCH = "record_patch"


class ActionValueKind(StrEnum):
    """Tagged scalar value forms with no Odoo command language."""

    BOOLEAN = "boolean"
    DATE = "date"
    DATETIME = "datetime"
    DECIMAL = "decimal"
    INTEGER = "integer"
    MANY2ONE = "many2one"
    SELECTION = "selection"
    TEXT = "text"


class ActionValue(BaseModel):
    """One explicitly typed value; tags prevent JSON coercion ambiguity."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    kind: ActionValueKind
    value: bool | int | str | None

    @model_validator(mode="after")
    def validate_tagged_value(self) -> Self:
        value = self.value
        value_type = type(value)
        if value is None:
            return self
        if self.kind is ActionValueKind.BOOLEAN and value_type is bool:
            return self
        if self.kind in {ActionValueKind.INTEGER, ActionValueKind.MANY2ONE}:
            if (
                isinstance(value, int)
                and not isinstance(value, bool)
                and (self.kind is ActionValueKind.INTEGER or value > 0)
            ):
                return self
            raise ValueError("integer action value is invalid")
        if not isinstance(value, str) or len(value) > MAX_ACTION_VALUE_TEXT:
            raise ValueError("text action value is invalid")
        if self.kind is ActionValueKind.DECIMAL:
            if _DECIMAL_PATTERN.fullmatch(value) is None:
                raise ValueError("decimal action value is not canonical")
            try:
                decimal = Decimal(value)
            except InvalidOperation:
                raise ValueError("decimal action value is invalid") from None
            normalized = format(decimal, "f")
            if "." in normalized:
                normalized = normalized.rstrip("0").rstrip(".")
            if normalized in {"", "-0"}:
                normalized = "0"
            if value != normalized:
                raise ValueError("decimal action value is not canonical")
        elif self.kind is ActionValueKind.DATE:
            if _DATE_PATTERN.fullmatch(value) is None:
                raise ValueError("date action value is not canonical")
            try:
                date.fromisoformat(value)
            except ValueError:
                raise ValueError("date action value is invalid") from None
        elif self.kind is ActionValueKind.DATETIME:
            if _DATETIME_PATTERN.fullmatch(value) is None:
                raise ValueError("datetime action value is not canonical")
            try:
                datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                raise ValueError("datetime action value is invalid") from None
        elif self.kind is ActionValueKind.SELECTION:
            if not value or len(value) > 256:
                raise ValueError("selection action value is invalid")
        elif self.kind is not ActionValueKind.TEXT:
            raise ValueError("action value kind does not match value")
        return self


class ActionTarget(BaseModel):
    """Exactly one Odoo record targeted by a proposal."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    model: ModelName
    record_id: PositiveId


class ActionFieldChange(BaseModel):
    """One field assignment in a record patch."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    field: FieldName
    value: ActionValue


class ActionProposalPayload(BaseModel):
    """Host-validated payload whose exact canonical bytes may be previewed."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    format_version: Literal[1] = ACTION_PAYLOAD_FORMAT_VERSION
    proposal_id: UUID
    turn_id: UUID
    action_kind: Literal[ActionKind.RECORD_PATCH] = ActionKind.RECORD_PATCH
    instance_id: str = Field(min_length=1, max_length=255)
    database: str = Field(min_length=1, max_length=128)
    uid: PositiveId
    company_id: PositiveId
    allowed_company_ids: tuple[PositiveId, ...] = Field(
        min_length=1, max_length=MAX_ACTION_COMPANIES
    )
    target: ActionTarget
    changes: tuple[ActionFieldChange, ...] = Field(min_length=1, max_length=MAX_ACTION_FIELDS)
    policy_revision: Revision
    schema_revision: Revision

    @field_validator("database", "instance_id")
    @classmethod
    def validate_binding_text(cls, value: str) -> str:
        if value != value.strip() or any(ord(character) < 32 for character in value):
            raise ValueError("action binding is invalid")
        return value

    @model_validator(mode="after")
    def validate_binding_and_changes(self) -> Self:
        if self.company_id not in self.allowed_company_ids:
            raise ValueError("effective company must be allowed")
        if tuple(self.allowed_company_ids) != tuple(sorted(self.allowed_company_ids)):
            raise ValueError("allowed companies must be canonically ordered")
        fields = tuple(change.field for change in self.changes)
        if len(fields) != len(set(fields)):
            raise ValueError("action fields must be unique")
        return self


class ActionPreviewChange(BaseModel):
    """Sanitized before/after pair displayed to the user."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    field: FieldName
    label: str | None = Field(default=None, min_length=1, max_length=256)
    before: ActionValue
    after: ActionValue


class ActionPreviewSummary(BaseModel):
    """Bounded durable summary of the exact preview shown for approval."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    proposal_id: UUID
    target: ActionTarget
    changes: tuple[ActionPreviewChange, ...] = Field(min_length=1, max_length=MAX_ACTION_FIELDS)
    warnings: tuple[str, ...] = Field(default=(), max_length=MAX_ACTION_WARNINGS)

    @field_validator("warnings")
    @classmethod
    def validate_warnings(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(not 1 <= len(item) <= 512 for item in value):
            raise ValueError("preview warning is invalid")
        return value


class ActionPreview(BaseModel):
    """Checked preview binding proposal, observed state, policy and expiry."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    preview_id: UUID
    summary: ActionPreviewSummary
    payload_fingerprint: Fingerprint
    precondition_fingerprint: Fingerprint
    policy_revision: Revision
    schema_revision: Revision
    observed_at: AwareDatetime
    expires_at: AwareDatetime

    @model_validator(mode="after")
    def validate_expiry(self) -> Self:
        if self.expires_at <= self.observed_at:
            raise ValueError("preview expiry must follow observation")
        return self


class EffectiveWriteFieldSchema(BaseModel):
    """One runtime-visible field that is eligible for the bounded patch policy."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    name: FieldName
    label: str | None = Field(default=None, min_length=1, max_length=256)
    field_type: FieldName
    value_kind: ActionValueKind
    relation: ModelName | None = None
    required: bool
    selection: tuple[str, ...] | None = Field(default=None, max_length=64)

    @model_validator(mode="after")
    def validate_relation_and_selection(self) -> Self:
        if (self.value_kind is ActionValueKind.MANY2ONE) != (self.relation is not None):
            raise ValueError("write field relation metadata is invalid")
        if self.value_kind is ActionValueKind.SELECTION:
            if not self.selection or len(self.selection) != len(set(self.selection)):
                raise ValueError("write field selection metadata is invalid")
        elif self.selection is not None:
            raise ValueError("selection metadata is only valid for selection fields")
        return self


class EffectiveWriteSchema(BaseModel):
    """Bounded write capability evidence for one model and effective user."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_id: Fingerprint
    instance_id: str = Field(min_length=1, max_length=255)
    database: str = Field(min_length=1, max_length=128)
    model: ModelName
    label: str | None = Field(default=None, min_length=1, max_length=256)
    write_access: bool
    fields: dict[FieldName, EffectiveWriteFieldSchema] = Field(max_length=64)
    source: Literal["runtime"] = "runtime"
    captured_for_user: PositiveId
    company_id: PositiveId
    allowed_company_ids: tuple[PositiveId, ...] = Field(
        min_length=1, max_length=MAX_ACTION_COMPANIES
    )
    policy_revision: Revision
    captured_at: AwareDatetime

    @field_validator("database", "instance_id")
    @classmethod
    def validate_context_binding_text(cls, value: str) -> str:
        if value != value.strip() or any(ord(character) < 32 for character in value):
            raise ValueError("effective write schema binding is invalid")
        return value

    @model_validator(mode="after")
    def validate_field_mapping(self) -> Self:
        if self.company_id not in self.allowed_company_ids:
            raise ValueError("effective company must be allowed")
        if self.allowed_company_ids != tuple(sorted(self.allowed_company_ids)):
            raise ValueError("allowed companies must be canonically ordered")
        if any(name != field.name for name, field in self.fields.items()):
            raise ValueError("effective write schema field keys must match names")
        if tuple(self.fields) != tuple(sorted(self.fields)):
            raise ValueError("effective write schema fields must be deterministically ordered")
        if not self.write_access and self.fields:
            raise ValueError("a non-writeable model cannot expose write fields")
        return self
