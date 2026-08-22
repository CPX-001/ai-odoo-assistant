"""Bounded requests and results shared with log providers."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from odoo_ai.contracts.evidence import Evidence


class LogCapabilityState(StrEnum):
    OPERATIONAL = "OPERATIONAL"
    NOT_FOUND = "NOT_FOUND"
    NO_PERMISSION = "NO_PERMISSION"
    ERROR = "ERROR"


class LogSearchRequest(BaseModel):
    """A time-bounded and size-bounded log search request."""

    model_config = ConfigDict(extra="forbid")

    from_ts: datetime | None = None
    to_ts: datetime | None = None
    terms: list[str] = Field(default_factory=list, max_length=8)
    max_lines: int = Field(gt=0, le=200)
    max_bytes: int = Field(gt=0, le=65_536)

    @field_validator("terms")
    @classmethod
    def validate_terms(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(term.casefold() for term in value)):
            raise ValueError("log terms must be unique")
        if any(
            not 1 <= len(term) <= 128
            or term != term.strip()
            or any(ord(character) < 32 for character in term)
            for term in value
        ):
            raise ValueError("log terms must be bounded literal text")
        return value

    @model_validator(mode="after")
    def validate_window(self) -> "LogSearchRequest":
        if self.from_ts is not None and self.from_ts.tzinfo is None:
            raise ValueError("from_ts must be timezone-aware")
        if self.to_ts is not None and self.to_ts.tzinfo is None:
            raise ValueError("to_ts must be timezone-aware")
        if (
            self.from_ts is not None
            and self.to_ts is not None
            and self.to_ts < self.from_ts
        ):
            raise ValueError("to_ts must not precede from_ts")
        return self


class TimestampRange(BaseModel):
    """Observed time range covered by a log excerpt."""

    model_config = ConfigDict(extra="forbid")

    from_ts: datetime | None = None
    to_ts: datetime | None = None


class LogCorrelation(StrEnum):
    """Strength of the link between a log excerpt and the current turn."""

    DIRECT = "direct"
    TEMPORAL_INFERENCE = "temporal_inference"


class LogPointer(BaseModel):
    """Opaque provider ref that never contains a file path or journal unit."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: str = Field(min_length=1, max_length=32)
    reference: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")


class LogEvidence(BaseModel):
    """Redacted, bounded evidence returned by a log provider."""

    model_config = ConfigDict(extra="forbid")

    provider: str
    timestamp_range: TimestampRange
    excerpt: str
    traceback_fingerprint: str | None = None
    correlation: LogCorrelation
    pointer: LogPointer | None = None
    truncated: bool = False
    truncation_reasons: tuple[str, ...] = Field(default=(), max_length=8)
    timestamp_parse_complete: bool = True
    matched_terms: tuple[str, ...] = Field(default=(), max_length=8)
    line_count: int = Field(default=0, ge=0, le=200)
    byte_count: int = Field(default=0, ge=0, le=65_536)
    occurrence_count: int = Field(default=1, gt=0)
    evidence: Evidence | None = None
