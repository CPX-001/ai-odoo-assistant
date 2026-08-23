"""Narrow browser-safe contracts for the M5 HOW_TO workflow."""

from pathlib import PurePosixPath
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

from odoo_ai.contracts.agent import AnswerConfidence
from odoo_ai.contracts.context import Workflow
from odoo_ai.contracts.delegation import ContextReadTurnRequest
from odoo_ai.contracts.knowledge import (
    LOCALE_PATTERN,
    LOGICAL_ID_PATTERN,
    KnowledgeMediaType,
)
from odoo_ai.contracts.navigation import NavigationViewMode


class HowToTurnRequest(ContextReadTurnRequest):
    """Authenticated Odoo-server ingress for one read-only HOW_TO turn."""


class NavigationCitation(BaseModel):
    """One visible logical menu/action checked for the effective user."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["navigation"] = "navigation"
    evidence_id: UUID
    menu_id: int = Field(strict=True, gt=0)
    path: tuple[Annotated[str, Field(min_length=1, max_length=256)], ...] = Field(
        min_length=1, max_length=8
    )
    target_model: str | None = Field(
        default=None, max_length=128, pattern=r"^[A-Za-z_][A-Za-z0-9_.]{0,127}$"
    )
    view_modes: tuple[NavigationViewMode, ...] = Field(default=(), max_length=7)
    captured_at: AwareDatetime


class SchemaFieldCitation(BaseModel):
    """Browser-safe runtime field metadata."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")
    label: str | None = Field(default=None, max_length=256)
    field_type: str = Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")


class SchemaCitation(BaseModel):
    """One fingerprinted effective runtime schema."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["schema"] = "schema"
    evidence_id: UUID
    model: str = Field(pattern=r"^[A-Za-z_][A-Za-z0-9_.]{0,127}$")
    schema_id: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    fields: tuple[SchemaFieldCitation, ...] = Field(min_length=1, max_length=64)
    captured_at: AwareDatetime


class DocumentCitation(BaseModel):
    """Logical current knowledge excerpt; physical paths are never exposed."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["document"] = "document"
    evidence_id: UUID
    provider_id: str = Field(pattern=LOGICAL_ID_PATTERN, max_length=128)
    document_id: str = Field(min_length=1, max_length=1024)
    title: str = Field(min_length=1, max_length=512)
    locale: str | None = Field(default=None, pattern=LOCALE_PATTERN, max_length=64)
    media_type: KnowledgeMediaType
    ordinal: int = Field(ge=0, le=65_535)
    start_line: int = Field(gt=0)
    end_line: int = Field(gt=0)
    fingerprint: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")

    @field_validator("document_id")
    @classmethod
    def validate_document_id(cls, value: str) -> str:
        if "\\" in value:
            raise ValueError("document_id must use POSIX separators")
        path = PurePosixPath(value)
        if path.is_absolute() or str(path) != value or any(
            part in {"", ".", ".."} for part in path.parts
        ):
            raise ValueError("document_id must be relative and normalized")
        return value

    @model_validator(mode="after")
    def validate_line_range(self) -> "DocumentCitation":
        if self.end_line < self.start_line:
            raise ValueError("document citation line range is invalid")
        return self


HowToCitation = Annotated[
    NavigationCitation | SchemaCitation | DocumentCitation,
    Field(discriminator="kind"),
]


class HowToTurnResponse(BaseModel):
    """Sanitized HOW_TO result with only logical, checked citations."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    turn_id: UUID
    status: Literal["ok"] = "ok"
    answer_markdown: str = Field(min_length=1, max_length=16_384)
    workflow: Literal[Workflow.HOW_TO] = Workflow.HOW_TO
    confidence: AnswerConfidence
    limitations: tuple[Annotated[str, Field(min_length=1, max_length=1_024)], ...] = Field(
        default=(), max_length=8
    )
    citations: tuple[HowToCitation, ...] = Field(default=(), max_length=24)
    completed_at: AwareDatetime
