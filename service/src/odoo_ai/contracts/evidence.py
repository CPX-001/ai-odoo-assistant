"""Evidence contracts produced by deterministic providers and tools."""

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue


class EvidenceKind(StrEnum):
    """Supported origins or subjects for an evidence unit."""

    RECORD = "record"
    METADATA = "metadata"
    SOURCE = "source"
    LOG = "log"
    DOCUMENT = "document"
    GENERAL = "general"


class EvidenceStatus(StrEnum):
    """Degree to which an evidence unit has been verified."""

    CHECKED = "checked"
    INFERRED = "inferred"
    GENERAL = "general"
    UNKNOWN = "unknown"


class EvidenceSensitivity(StrEnum):
    """Sensitivity classification carried with an evidence unit."""

    NORMAL = "normal"
    TECHNICAL = "technical"
    SENSITIVE = "sensitive"


class Evidence(BaseModel):
    """A citable, structured unit of evidence with provenance metadata."""

    model_config = ConfigDict(extra="forbid")

    evidence_id: UUID
    kind: EvidenceKind
    status: EvidenceStatus
    title: str
    summary: str
    payload: dict[str, JsonValue] = Field(default_factory=dict)
    pointer: dict[str, JsonValue] | None = None
    observed_at: datetime | None = None
    sensitivity: EvidenceSensitivity
    fingerprint: str | None = None
