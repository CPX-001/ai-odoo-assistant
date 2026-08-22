"""Stable contracts for bounded, incremental source indexing."""

import re
from datetime import datetime
from enum import StrEnum
from pathlib import PurePosixPath
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator, model_validator

from odoo_ai.contracts.evidence import Evidence

FINGERPRINT_PATTERN = r"^sha256:[0-9a-f]{64}$"
MODULE_PATTERN = r"^[A-Za-z0-9_]+$"


class ScanStatus(StrEnum):
    """Lifecycle states for one source scan."""

    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class SourceFileKind(StrEnum):
    """Static source types accepted by the M3 scanner."""

    MANIFEST = "manifest"
    PYTHON = "python"
    XML = "xml"
    CSV = "csv"
    OTHER = "other"


class SourceCapabilityState(StrEnum):
    """Operational state of the bounded source subsystem."""

    DETECTED = "DETECTED"
    NOT_FOUND = "NOT_FOUND"
    NO_PERMISSION = "NO_PERMISSION"
    ERROR = "ERROR"


class SourceProvenance(StrEnum):
    """Conservative module provenance backed by explicit evidence."""

    OFFICIAL = "official"
    OCA = "oca"
    REMOTE_KNOWN = "remote_known"
    MANUAL = "manual"
    THIRD_PARTY_OR_CUSTOM = "third_party_or_custom"
    UNKNOWN = "unknown"


class ManifestStatus(StrEnum):
    EVALUATED = "evaluated"
    UNEVALUABLE = "unevaluable"
    INVALID = "invalid"


class ManifestMetadata(BaseModel):
    """Bounded literal metadata extracted without importing an addon."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: ManifestStatus
    name: str | None = Field(default=None, max_length=512)
    version: str | None = Field(default=None, max_length=128)
    depends: tuple[str, ...] = Field(default=(), max_length=2048)
    data: tuple[str, ...] = Field(default=(), max_length=2048)
    assets: dict[str, JsonValue] = Field(default_factory=dict, max_length=512)
    license: str | None = Field(default=None, max_length=128)


class InstanceInventory(BaseModel):
    """Narrow machine-authenticated runtime metadata returned by Odoo."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    database: str = Field(min_length=1, max_length=128)
    server_version: str = Field(min_length=1, max_length=64)
    installed_modules: tuple[str, ...] = Field(max_length=4096)
    addons_roots: tuple[str, ...] = Field(max_length=128)
    captured_at: datetime

    @field_validator("installed_modules")
    @classmethod
    def validate_installed_modules(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(
            not module
            or len(module) > 255
            or re.fullmatch(MODULE_PATTERN, module) is None
            for module in value
        ):
            raise ValueError("installed module names must be bounded")
        if len(value) != len(set(value)):
            raise ValueError("installed modules must be unique")
        return value

    @field_validator("addons_roots")
    @classmethod
    def validate_addons_roots(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(not root or len(root) > 4096 or root != root.strip() for root in value):
            raise ValueError("addons roots must be bounded non-empty paths")
        if len(value) != len(set(value)):
            raise ValueError("addons roots must be unique")
        return value


class ScanRun(BaseModel):
    """Bounded source scan state for one Assistant instance."""

    model_config = ConfigDict(extra="forbid")

    scan_id: UUID
    instance_id: str = Field(min_length=1, max_length=255)
    status: ScanStatus
    started_at: datetime
    completed_at: datetime | None = None
    fingerprint: str | None = Field(default=None, pattern=FINGERPRINT_PATTERN)
    error_code: str | None = Field(default=None, min_length=1, max_length=128)

    @model_validator(mode="after")
    def validate_lifecycle(self) -> "ScanRun":
        if self.status is ScanStatus.RUNNING and self.completed_at is not None:
            raise ValueError("running scan cannot have completed_at")
        if self.status is not ScanStatus.RUNNING and self.completed_at is None:
            raise ValueError("terminal scan requires completed_at")
        if self.status is ScanStatus.SUCCEEDED and self.error_code is not None:
            raise ValueError("successful scan cannot have error_code")
        return self


class SourceRef(BaseModel):
    """Stable file pointer used instead of accepting a filesystem path."""

    model_config = ConfigDict(extra="forbid")

    source_file_id: UUID
    fingerprint: str = Field(pattern=FINGERPRINT_PATTERN)
    start_line: int | None = Field(default=None, gt=0)
    end_line: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def validate_lines(self) -> "SourceRef":
        if (self.start_line is None) != (self.end_line is None):
            raise ValueError("start_line and end_line must be provided together")
        if (
            self.start_line is not None
            and self.end_line is not None
            and self.end_line < self.start_line
        ):
            raise ValueError("end_line must not precede start_line")
        return self


class SourceFile(BaseModel):
    """Indexed metadata for a file without persisting its full contents."""

    model_config = ConfigDict(extra="forbid")

    file_id: UUID
    scan_id: UUID
    instance_id: str = Field(min_length=1, max_length=255)
    module: str = Field(pattern=MODULE_PATTERN, max_length=255)
    kind: SourceFileKind
    logical_path: str = Field(min_length=1, max_length=1024)
    fingerprint: str = Field(pattern=FINGERPRINT_PATTERN)
    size_bytes: int = Field(ge=0)
    provenance: SourceProvenance = SourceProvenance.UNKNOWN
    metadata: dict[str, JsonValue] | None = None
    stale: bool = False

    @field_validator("logical_path")
    @classmethod
    def validate_logical_path(cls, value: str) -> str:
        if "\\" in value:
            raise ValueError("logical_path must use POSIX separators")
        path = PurePosixPath(value)
        if (
            path.is_absolute()
            or str(path) != value
            or any(part in {"", ".", ".."} for part in path.parts)
        ):
            raise ValueError("logical_path must be relative and normalized")
        return value


class SourceSymbol(BaseModel):
    """A structural symbol extracted from one fingerprinted source file."""

    model_config = ConfigDict(extra="forbid")

    symbol_id: UUID
    module: str = Field(pattern=MODULE_PATTERN, max_length=255)
    kind: str = Field(min_length=1, max_length=64)
    model: str | None = Field(default=None, min_length=1, max_length=255)
    name: str = Field(min_length=1, max_length=255)
    logical_path: str = Field(min_length=1, max_length=1024)
    start_line: int = Field(gt=0)
    end_line: int = Field(gt=0)
    fingerprint: str = Field(pattern=FINGERPRINT_PATTERN)
    ref: SourceRef
    details: dict[str, JsonValue] | None = None

    @model_validator(mode="after")
    def validate_pointer(self) -> "SourceSymbol":
        SourceFile.validate_logical_path(self.logical_path)
        if self.end_line < self.start_line:
            raise ValueError("end_line must not precede start_line")
        if self.ref.fingerprint != self.fingerprint:
            raise ValueError("source ref fingerprint must match symbol fingerprint")
        if (self.ref.start_line, self.ref.end_line) != (self.start_line, self.end_line):
            raise ValueError("source ref lines must match symbol lines")
        return self


class XmlRecord(BaseModel):
    """A static XML record declaration and its stable source pointer."""

    model_config = ConfigDict(extra="forbid")

    record_id: UUID
    module: str = Field(pattern=MODULE_PATTERN, max_length=255)
    xml_id: str = Field(min_length=1, max_length=512)
    model: str | None = Field(default=None, min_length=1, max_length=255)
    logical_path: str = Field(min_length=1, max_length=1024)
    fingerprint: str = Field(pattern=FINGERPRINT_PATTERN)
    ref: SourceRef
    declaration: dict[str, JsonValue] | None = None

    @model_validator(mode="after")
    def validate_pointer(self) -> "XmlRecord":
        SourceFile.validate_logical_path(self.logical_path)
        if self.ref.fingerprint != self.fingerprint:
            raise ValueError("source ref fingerprint must match XML record fingerprint")
        return self


class SourceMatchReason(StrEnum):
    EXACT = "exact"
    NORMALIZED = "normalized"


class FindSymbolRequest(BaseModel):
    """Bounded structural lookup with no filesystem path input."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    query: str = Field(min_length=1, max_length=255)
    model: str | None = Field(default=None, min_length=1, max_length=255)
    module: str | None = Field(default=None, pattern=MODULE_PATTERN, max_length=255)
    max_results: int = Field(default=10, gt=0, le=20)

    @field_validator("query", "model")
    @classmethod
    def reject_surrounding_whitespace(cls, value: str | None) -> str | None:
        if value is not None and value != value.strip():
            raise ValueError("source query values must be normalized")
        return value


class SourceCandidate(BaseModel):
    """One current structural match emitted by the source index."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    symbol_id: UUID
    module: str = Field(pattern=MODULE_PATTERN, max_length=255)
    kind: str = Field(min_length=1, max_length=64)
    model: str | None = Field(default=None, min_length=1, max_length=255)
    name: str = Field(min_length=1, max_length=255)
    logical_path: str = Field(min_length=1, max_length=1024)
    start_line: int = Field(gt=0)
    end_line: int = Field(gt=0)
    fingerprint: str = Field(pattern=FINGERPRINT_PATTERN)
    provenance: SourceProvenance
    ref: SourceRef
    score: int = Field(ge=0, le=100)
    match_reason: SourceMatchReason
    observed_at: datetime
    details: dict[str, JsonValue] | None = None

    @model_validator(mode="after")
    def validate_candidate(self) -> "SourceCandidate":
        SourceFile.validate_logical_path(self.logical_path)
        if self.end_line < self.start_line:
            raise ValueError("end_line must not precede start_line")
        if self.ref.fingerprint != self.fingerprint:
            raise ValueError("candidate ref fingerprint must match")
        if (self.ref.start_line, self.ref.end_line) != (
            self.start_line,
            self.end_line,
        ):
            raise ValueError("candidate ref lines must match")
        return self


class FindSymbolResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    candidates: tuple[SourceCandidate, ...] = Field(max_length=20)


class FindModelExtensionsRequest(BaseModel):
    """Find declared Python model relationships without claiming runtime order."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    model: str = Field(min_length=1, max_length=255)
    module: str | None = Field(default=None, pattern=MODULE_PATTERN, max_length=255)
    max_results: int = Field(default=30, gt=0, le=50)

    @field_validator("model")
    @classmethod
    def validate_model(cls, value: str) -> str:
        if value != value.strip():
            raise ValueError("model must be normalized")
        return value


class ModelExtensionGroup(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    module: str = Field(pattern=MODULE_PATTERN, max_length=255)
    logical_path: str = Field(min_length=1, max_length=1024)
    provenance: SourceProvenance
    relationships: tuple[SourceCandidate, ...] = Field(min_length=1, max_length=50)
    runtime_order_checked: bool = False


class FindModelExtensionsResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    model: str = Field(min_length=1, max_length=255)
    groups: tuple[ModelExtensionGroup, ...] = Field(max_length=50)


class ReadExcerptRequest(BaseModel):
    """Read around an exact indexed ref; a client path is never accepted."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    ref: SourceRef
    context_before: int = Field(default=2, ge=0, le=20)
    context_after: int = Field(default=2, ge=0, le=20)
    max_lines: int = Field(default=40, gt=0, le=80)
    max_bytes: int = Field(default=16_384, gt=0, le=32_768)

    @model_validator(mode="after")
    def require_symbol_lines(self) -> "ReadExcerptRequest":
        if self.ref.start_line is None or self.ref.end_line is None:
            raise ValueError("excerpt ref requires indexed lines")
        return self


class SourceExcerptLine(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    number: int = Field(gt=0)
    text: str = Field(max_length=32_768)


class SourceExcerpt(BaseModel):
    """Bounded current source fragment and its checked evidence wrapper."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    ref: SourceRef
    module: str = Field(pattern=MODULE_PATTERN, max_length=255)
    logical_path: str = Field(min_length=1, max_length=1024)
    lines: tuple[SourceExcerptLine, ...] = Field(min_length=1, max_length=80)
    evidence: Evidence
