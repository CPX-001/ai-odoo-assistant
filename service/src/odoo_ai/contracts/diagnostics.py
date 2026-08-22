"""Bounded admin contracts for observable M3 source/log diagnostics."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from odoo_ai.contracts.logs import LogEvidence
from odoo_ai.contracts.source import (
    SourceCandidate,
    SourceCapabilityState,
    SourceExcerpt,
)


class EmptyDiagnosticsRequest(BaseModel):
    """Explicitly reject arbitrary options on fixed admin actions."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class SourceScanMetricsView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    modules: int = Field(ge=0)
    files_seen: int = Field(ge=0)
    files_extracted: int = Field(ge=0)
    files_unchanged: int = Field(ge=0)
    bytes_hashed: int = Field(ge=0)
    stale_files: int = Field(ge=0)


class SourceScanDiagnostics(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    state: SourceCapabilityState
    scan_id: UUID | None = None
    fingerprint: str | None = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")
    metrics: SourceScanMetricsView
    error_codes: tuple[str, ...] = Field(default=(), max_length=32)


class SourceStatusDiagnostics(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    state: SourceCapabilityState | Literal["UNKNOWN"]
    scan_status: Literal["running", "succeeded", "failed", "unknown"]
    scan_id: UUID | None = None
    fingerprint: str | None = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")
    completed_at: datetime | None = None


class SourceTestDiagnostics(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    query: Literal["action_confirm"] = "action_confirm"
    model: Literal["sale.order"] = "sale.order"
    candidate: SourceCandidate
    excerpt: SourceExcerpt


class LogTestDiagnostics(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    state: Literal["OPERATIONAL"] = "OPERATIONAL"
    provider: Literal["file", "journal"]
    results: tuple[LogEvidence, ...] = Field(max_length=20)


class TracebackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    fingerprint: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    max_bytes: int = Field(default=16_384, gt=0, le=65_536)
