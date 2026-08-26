"""Versioned read-only delegation claims for residual Odoo callbacks."""

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Final, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator

from odoo_ai.contracts.context import UserExecutionContext
from odoo_ai.contracts.evidence import Evidence
from odoo_ai.contracts.records import RecordSnapshot
from odoo_ai.contracts.screen_context import ScreenContext

DELEGATION_FORMAT_VERSION: Final = 1
MAX_ALLOWED_COMPANY_IDS: Final = 16
MAX_DELEGATED_RECORD_IDS: Final = 8
MAX_DELEGATION_SCOPES: Final = 2
MAX_DELEGATION_TTL_SECONDS: Final = 120
MAX_CONTEXT_MESSAGE_LENGTH: Final = 4_000
MAX_DELEGATED_FIELDS: Final = 64

PositiveId = Annotated[int, Field(strict=True, gt=0)]


class DelegationScope(StrEnum):
    """Explicit read-only authority signed for a residual callback."""

    FIELDS_GET = "fields_get"
    NAVIGATION = "navigation"
    READ_RECORDS = "read_records"


class DelegationClaims(BaseModel):
    """Strict authority signed by Odoo and treated as opaque by the service."""

    model_config = ConfigDict(extra="forbid", strict=True)

    format_version: Literal[1] = DELEGATION_FORMAT_VERSION
    jti: str = Field(min_length=22, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    turn_id: UUID
    database: str = Field(min_length=1, max_length=128)
    uid: PositiveId
    company_id: PositiveId
    allowed_company_ids: list[PositiveId] = Field(min_length=1, max_length=MAX_ALLOWED_COMPANY_IDS)
    lang: str | None = Field(default=None, min_length=2, max_length=35)
    model: str | None = Field(default=None, min_length=1, max_length=128, pattern=r"^[A-Za-z_][A-Za-z0-9_.]*$")
    record_ids: list[PositiveId] = Field(default_factory=list, max_length=MAX_DELEGATED_RECORD_IDS)
    scopes: list[DelegationScope] = Field(min_length=1, max_length=MAX_DELEGATION_SCOPES)
    issued_at: int = Field(strict=True, ge=0)
    expires_at: int = Field(strict=True, ge=0)
    max_records: int = Field(strict=True, ge=0, le=MAX_DELEGATED_RECORD_IDS)
    max_fields: int = Field(strict=True, ge=1, le=MAX_DELEGATED_FIELDS)

    @field_validator("database")
    @classmethod
    def validate_database_binding(cls, value: str) -> str:
        if value != value.strip() or any(ord(character) < 32 for character in value):
            raise ValueError("database binding is invalid")
        return value

    @field_validator("allowed_company_ids", "record_ids", "scopes")
    @classmethod
    def validate_unique_list(cls, value: list[object]) -> list[object]:
        if len(value) != len(set(value)):
            raise ValueError("delegation list values must be unique")
        return value

    @model_validator(mode="after")
    def validate_authority_shape(self) -> Self:
        if self.company_id not in self.allowed_company_ids:
            raise ValueError("effective company must be allowed")
        ttl = self.expires_at - self.issued_at
        if not 0 < ttl <= MAX_DELEGATION_TTL_SECONDS:
            raise ValueError("delegation TTL is invalid")
        if self.max_records > len(self.record_ids):
            raise ValueError("record limit exceeds delegated records")
        if DelegationScope.READ_RECORDS in self.scopes and (
            self.model is None or not self.record_ids or self.max_records < 1
        ):
            raise ValueError("record scope requires bounded record authority")
        if DelegationScope.FIELDS_GET in self.scopes and self.model is None:
            raise ValueError("metadata scope requires a model")
        return self


class OdooGatewayReference(BaseModel):
    """Server-side routing key; endpoint resolution remains adapter configuration."""

    model_config = ConfigDict(extra="forbid", strict=True)

    database: str = Field(min_length=1, max_length=128)

    @field_validator("database")
    @classmethod
    def validate_database_binding(cls, value: str) -> str:
        if value != value.strip() or any(ord(character) < 32 for character in value):
            raise ValueError("database binding is invalid")
        return value


class ContextReadTurnRequest(BaseModel):
    """Authenticated Odoo-server ingress for the deterministic current-record read."""

    model_config = ConfigDict(extra="forbid")

    turn_id: UUID
    message: str = Field(min_length=1, max_length=MAX_CONTEXT_MESSAGE_LENGTH)
    screen: ScreenContext
    user: UserExecutionContext
    delegation_token: SecretStr = Field(min_length=1, max_length=4096)
    gateway: OdooGatewayReference


class ContextReadTurnResponse(BaseModel):
    """Sanitized deterministic result returned to the authenticated Odoo server."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    turn_id: UUID
    status: Literal["ok"] = "ok"
    message: str = Field(min_length=1, max_length=512)
    instance_state: Literal["detected", "unknown"]
    instance_id: str | None = Field(default=None, max_length=255)
    fields_read: tuple[str, ...] = Field(min_length=1, max_length=4)
    record: RecordSnapshot
    evidence: Evidence
    completed_at: datetime
