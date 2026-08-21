"""Stable references and snapshots of Odoo records."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, JsonValue


class RecordRef(BaseModel):
    """Minimal identity of a record without loading business data."""

    model_config = ConfigDict(extra="forbid")

    model: str
    id: int
    display_name: str | None = None


class RecordSnapshot(BaseModel):
    """Fields read for a record at a known time with explicit provenance."""

    model_config = ConfigDict(extra="forbid")

    record: RecordRef
    fields: dict[str, JsonValue] = Field(default_factory=dict)
    captured_at: datetime
    provenance: dict[str, JsonValue] = Field(default_factory=dict)
