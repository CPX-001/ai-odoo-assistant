"""Stable contracts for bounded, incremental source indexing."""

import re
from datetime import datetime
from enum import StrEnum
from pathlib import PurePosixPath
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

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

    @model_validator(mode="after")
    def validate_pointer(self) -> "XmlRecord":
        SourceFile.validate_logical_path(self.logical_path)
        if self.ref.fingerprint != self.fingerprint:
            raise ValueError("source ref fingerprint must match XML record fingerprint")
        return self
