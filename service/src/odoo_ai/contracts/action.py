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
MAX_ACTION_FIELDS: Final = 16
MAX_ACTION_WARNINGS: Final = 8
MAX_ACTION_VALUE_TEXT: Final = 4_000
SALE_ORDER_CONFIRM_ACTION_ID: Final = "sale.order.confirm.v1"
SALE_ORDER_CONFIRM_SPEC_REVISION: Final = "sale-order-confirm-spec-v1"
RECORD_ARCHIVE_ACTION_ID: Final = "record.archive.v1"
RECORD_ARCHIVE_SPEC_REVISION: Final = "record-archive-spec-v1"
RECORD_DELETE_ACTION_ID: Final = "record.delete.v1"
RECORD_DELETE_SPEC_REVISION: Final = "record-delete-spec-v1"
SALE_ORDER_BUILD_FLOW_ACTION_ID: Final = "sale.order.build_flow.v1"
SALE_ORDER_BUILD_FLOW_SPEC_REVISION: Final = "sale-order-build-flow-spec-v1"

BusinessActionId = Literal[
    "sale.order.confirm.v1",
    "record.archive.v1",
    "record.delete.v1",
    "sale.order.build_flow.v1",
]

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
    RECORD_CREATE = "record_create"
    BUSINESS_ACTION = "business_action"


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


class ActionCreateTarget(BaseModel):
    """A create target names a model but can never carry a caller-chosen id."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    model: ModelName


class SaleOrderBuildFlowArguments(BaseModel):
    """Typed inputs for the atomic sale-order construction flow."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    end_state: Literal["quotation", "sale_order", "invoice_draft"]
    partner_id: PositiveId | None = None
    partner_name: str | None = Field(default=None, min_length=1, max_length=256)
    create_synthetic_partner: bool = False
    product_id: PositiveId | None = None
    product_name: str | None = Field(default=None, min_length=1, max_length=256)
    create_synthetic_product: bool = False
    quantity: str = Field(pattern=r"^(?:[1-9][0-9]{0,5})(?:\.[0-9]{1,3})?$")
    price_unit: str | None = Field(
        default=None,
        pattern=r"^(?:0|[1-9][0-9]{0,12})(?:\.[0-9]{1,6})?$",
    )
    synthetic_data_authorized: bool = False

    @model_validator(mode="after")
    def validate_references_and_synthetic_data(self) -> Self:
        if (self.partner_id is None) == (not self.create_synthetic_partner):
            raise ValueError("exactly one partner source is required")
        if (self.product_id is None) == (not self.create_synthetic_product):
            raise ValueError("exactly one product source is required")
        if self.create_synthetic_partner:
            if not self.synthetic_data_authorized or not self.partner_name:
                raise ValueError("synthetic partner is not authorized")
            if not self.partner_name.upper().startswith("AI TEST"):
                raise ValueError("synthetic partner must be visibly marked")
        elif self.partner_name is not None:
            raise ValueError("partner_name is only valid for synthetic data")
        if self.create_synthetic_product:
            if not self.synthetic_data_authorized or not self.product_name:
                raise ValueError("synthetic product is not authorized")
            if not self.product_name.upper().startswith("AI TEST"):
                raise ValueError("synthetic product must be visibly marked")
        elif self.product_name is not None:
            raise ValueError("product_name is only valid for synthetic data")
        return self


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


class RecordCreateProposalPayload(BaseModel):
    """Canonical request to create exactly one record with bounded initial values."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    format_version: Literal[1] = ACTION_PAYLOAD_FORMAT_VERSION
    proposal_id: UUID
    turn_id: UUID
    action_kind: Literal[ActionKind.RECORD_CREATE] = ActionKind.RECORD_CREATE
    instance_id: str = Field(min_length=1, max_length=255)
    database: str = Field(min_length=1, max_length=128)
    uid: PositiveId
    company_id: PositiveId
    allowed_company_ids: tuple[PositiveId, ...] = Field(
        min_length=1, max_length=MAX_ACTION_COMPANIES
    )
    target: ActionCreateTarget
    values: tuple[ActionFieldChange, ...] = Field(min_length=1, max_length=MAX_ACTION_FIELDS)
    policy_revision: Revision
    schema_revision: Revision

    @field_validator("database", "instance_id")
    @classmethod
    def validate_binding_text(cls, value: str) -> str:
        if value != value.strip() or any(ord(character) < 32 for character in value):
            raise ValueError("action binding is invalid")
        return value

    @model_validator(mode="after")
    def validate_binding_and_values(self) -> Self:
        if self.company_id not in self.allowed_company_ids:
            raise ValueError("effective company must be allowed")
        if self.allowed_company_ids != tuple(sorted(set(self.allowed_company_ids))):
            raise ValueError("allowed companies must be canonically ordered and unique")
        fields = tuple(value.field for value in self.values)
        if len(fields) != len(set(fields)):
            raise ValueError("action fields must be unique")
        return self


class BusinessActionProposalPayload(BaseModel):
    """Canonical invocation of one versioned host-curated business action."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    format_version: Literal[1] = ACTION_PAYLOAD_FORMAT_VERSION
    proposal_id: UUID
    turn_id: UUID
    action_kind: Literal[ActionKind.BUSINESS_ACTION] = ActionKind.BUSINESS_ACTION
    action_id: BusinessActionId = SALE_ORDER_CONFIRM_ACTION_ID
    instance_id: str = Field(min_length=1, max_length=255)
    database: str = Field(min_length=1, max_length=128)
    uid: PositiveId
    company_id: PositiveId
    allowed_company_ids: tuple[PositiveId, ...] = Field(
        min_length=1, max_length=MAX_ACTION_COMPANIES
    )
    target: ActionTarget | ActionCreateTarget
    arguments: SaleOrderBuildFlowArguments | None = None
    policy_revision: Revision
    action_spec_revision: Revision = SALE_ORDER_CONFIRM_SPEC_REVISION

    @field_validator("database", "instance_id")
    @classmethod
    def validate_binding_text(cls, value: str) -> str:
        if value != value.strip() or any(ord(character) < 32 for character in value):
            raise ValueError("action binding is invalid")
        return value

    @model_validator(mode="after")
    def validate_closed_action(self) -> Self:
        if self.company_id not in self.allowed_company_ids or self.allowed_company_ids != tuple(
            sorted(set(self.allowed_company_ids))
        ):
            raise ValueError("invalid curated business action")
        expected_revision = {
            SALE_ORDER_CONFIRM_ACTION_ID: SALE_ORDER_CONFIRM_SPEC_REVISION,
            RECORD_ARCHIVE_ACTION_ID: RECORD_ARCHIVE_SPEC_REVISION,
            RECORD_DELETE_ACTION_ID: RECORD_DELETE_SPEC_REVISION,
            SALE_ORDER_BUILD_FLOW_ACTION_ID: SALE_ORDER_BUILD_FLOW_SPEC_REVISION,
        }[self.action_id]
        if self.action_spec_revision != expected_revision:
            raise ValueError("invalid curated business action revision")
        if self.action_id == SALE_ORDER_BUILD_FLOW_ACTION_ID:
            if (
                not isinstance(self.target, ActionCreateTarget)
                or self.target.model != "sale.order"
                or self.arguments is None
            ):
                raise ValueError("invalid sale order build flow")
        elif (
            not isinstance(self.target, ActionTarget)
            or self.arguments is not None
            or (
                self.action_id == SALE_ORDER_CONFIRM_ACTION_ID
                and self.target.model != "sale.order"
            )
        ):
            raise ValueError("invalid curated business action target")
        return self


ActionPayload = Annotated[
    ActionProposalPayload | RecordCreateProposalPayload | BusinessActionProposalPayload,
    Field(discriminator="action_kind"),
]


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


class ActionCreatePreviewValue(BaseModel):
    """One requested create value shown without pretending defaults are materialized."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    field: FieldName
    label: str | None = Field(default=None, min_length=1, max_length=256)
    value: ActionValue


class ActionCreatePreviewSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    proposal_id: UUID
    target: ActionCreateTarget
    values: tuple[ActionCreatePreviewValue, ...] = Field(min_length=1, max_length=MAX_ACTION_FIELDS)
    warnings: tuple[str, ...] = Field(default=(), max_length=MAX_ACTION_WARNINGS)

    @field_validator("warnings")
    @classmethod
    def validate_warnings(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(not 1 <= len(item) <= 512 for item in value):
            raise ValueError("preview warning is invalid")
        return value


class ActionCreatePreview(BaseModel):
    """Effect-free create preview bound to schema, references, actor and expiry."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    action_kind: Literal[ActionKind.RECORD_CREATE] = ActionKind.RECORD_CREATE
    preview_id: UUID
    summary: ActionCreatePreviewSummary
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


class BusinessActionPreviewSummary(BaseModel):
    """Effect-free, citable preview of one curated business action."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    proposal_id: UUID
    action_id: BusinessActionId = SALE_ORDER_CONFIRM_ACTION_ID
    target: ActionTarget | ActionCreateTarget
    display_name: str = Field(min_length=1, max_length=256)
    state_before: str | None = Field(default=None, max_length=64)
    expected_states: tuple[str, ...] = Field(default=("sale", "done"), min_length=1, max_length=8)
    details: dict[str, str | int | bool | None] = Field(default_factory=dict, max_length=16)
    warnings: tuple[str, ...] = Field(default=(), max_length=MAX_ACTION_WARNINGS)

    @field_validator("warnings")
    @classmethod
    def validate_warnings(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(not 1 <= len(item) <= 512 for item in value):
            raise ValueError("preview warning is invalid")
        return value

class BusinessActionPreview(BaseModel):
    """Checked preview for one exact allowlisted business action."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    action_kind: Literal[ActionKind.BUSINESS_ACTION] = ActionKind.BUSINESS_ACTION
    action_id: BusinessActionId = SALE_ORDER_CONFIRM_ACTION_ID
    preview_id: UUID
    summary: BusinessActionPreviewSummary
    payload_fingerprint: Fingerprint
    precondition_fingerprint: Fingerprint
    policy_revision: Revision
    action_spec_revision: Revision = SALE_ORDER_CONFIRM_SPEC_REVISION
    observed_at: AwareDatetime
    expires_at: AwareDatetime

    @model_validator(mode="after")
    def validate_expiry_and_action(self) -> Self:
        if self.expires_at <= self.observed_at or self.summary.action_id != self.action_id:
            raise ValueError("business action preview is invalid")
        return self


ActionPreviewContract = ActionPreview | ActionCreatePreview | BusinessActionPreview


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
    create_access: bool = False
    create_fields: dict[FieldName, EffectiveWriteFieldSchema] = Field(
        default_factory=dict, max_length=64
    )
    defaults: dict[FieldName, ActionValue] = Field(default_factory=dict, max_length=64)
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
        if any(name != field.name for name, field in self.create_fields.items()):
            raise ValueError("effective create schema field keys must match names")
        if tuple(self.create_fields) != tuple(sorted(self.create_fields)):
            raise ValueError("effective create schema fields must be deterministically ordered")
        if not self.create_access and self.create_fields:
            raise ValueError("a non-createable model cannot expose create fields")
        if tuple(self.defaults) != tuple(sorted(self.defaults)) or not set(
            self.defaults
        ).issubset(self.create_fields):
            raise ValueError("effective create defaults must match create fields")
        if not self.create_access and self.defaults:
            raise ValueError("a non-createable model cannot expose defaults")
        return self
