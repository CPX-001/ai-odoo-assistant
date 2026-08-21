"""Bounded requests and results shared with log providers."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class LogSearchRequest(BaseModel):
    """A time-bounded and size-bounded log search request."""

    model_config = ConfigDict(extra="forbid")

    from_ts: datetime | None = None
    to_ts: datetime | None = None
    terms: list[str] = Field(default_factory=list)
    max_lines: int = Field(gt=0, le=200)
    max_bytes: int = Field(gt=0)


class TimestampRange(BaseModel):
    """Observed time range covered by a log excerpt."""

    model_config = ConfigDict(extra="forbid")

    from_ts: datetime | None = None
    to_ts: datetime | None = None


class LogCorrelation(StrEnum):
    """Strength of the link between a log excerpt and the current turn."""

    DIRECT = "direct"
    TEMPORAL_INFERENCE = "temporal_inference"


class LogEvidence(BaseModel):
    """Redacted, bounded evidence returned by a log provider."""

    model_config = ConfigDict(extra="forbid")

    provider: str
    timestamp_range: TimestampRange
    excerpt: str
    traceback_fingerprint: str | None = None
    correlation: LogCorrelation
