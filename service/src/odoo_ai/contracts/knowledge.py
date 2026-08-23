"""Provider-neutral contracts for bounded document ingestion."""

from datetime import datetime
from enum import StrEnum
from pathlib import PurePosixPath
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from odoo_ai.contracts.evidence import Evidence
from odoo_ai.contracts.source import FINGERPRINT_PATTERN

LOGICAL_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$"
LOCALE_PATTERN = r"^[A-Za-z]{2,8}(?:[-_][A-Za-z0-9]{1,8})*$"


class KnowledgeMediaType(StrEnum):
    """Text formats deliberately supported by the initial provider."""

    TEXT = "text/plain"
    MARKDOWN = "text/markdown"


class KnowledgeDocumentStatus(StrEnum):
    CURRENT = "current"
    RETIRED = "retired"


class KnowledgeDocument(BaseModel):
    """One bounded logical document; physical paths never cross this boundary."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    provider_id: str = Field(pattern=LOGICAL_ID_PATTERN, max_length=128)
    document_id: str = Field(min_length=1, max_length=1024)
    title: str = Field(min_length=1, max_length=512)
    locale: str | None = Field(default=None, pattern=LOCALE_PATTERN, max_length=64)
    media_type: KnowledgeMediaType
    content: str = Field(max_length=2_097_152)
    fingerprint: str = Field(pattern=FINGERPRINT_PATTERN)
    size_bytes: int = Field(ge=0, le=2_097_152)
    observed_at: datetime
    modified_at: datetime | None = None

    @field_validator("document_id")
    @classmethod
    def validate_document_id(cls, value: str) -> str:
        if "\\" in value:
            raise ValueError("document_id must use POSIX separators")
        path = PurePosixPath(value)
        if (
            path.is_absolute()
            or str(path) != value
            or any(part in {"", ".", ".."} for part in path.parts)
        ):
            raise ValueError("document_id must be relative and normalized")
        return value

    @model_validator(mode="after")
    def validate_content_size(self) -> "KnowledgeDocument":
        if len(self.content.encode("utf-8")) != self.size_bytes:
            raise ValueError("size_bytes must describe normalized UTF-8 content")
        return self


class KnowledgeProviderIssue(BaseModel):
    """Sanitized provider issue without filesystem details."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$", max_length=64)
    document_id: str | None = Field(default=None, min_length=1, max_length=1024)

    @field_validator("document_id")
    @classmethod
    def validate_optional_document_id(cls, value: str | None) -> str | None:
        if value is not None:
            KnowledgeDocument.validate_document_id(value)
        return value


class KnowledgeProviderResult(BaseModel):
    """A bounded provider snapshot used by the ingestion application service."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    provider_id: str = Field(pattern=LOGICAL_ID_PATTERN, max_length=128)
    documents: tuple[KnowledgeDocument, ...] = Field(max_length=4096)
    issues: tuple[KnowledgeProviderIssue, ...] = Field(default=(), max_length=4096)
    complete: bool
    scanned_at: datetime

    @model_validator(mode="after")
    def validate_provider_scope(self) -> "KnowledgeProviderResult":
        if any(document.provider_id != self.provider_id for document in self.documents):
            raise ValueError("all documents must belong to the result provider")
        ids = [document.document_id for document in self.documents]
        if len(ids) != len(set(ids)):
            raise ValueError("provider result contains duplicate document ids")
        return self


class KnowledgeChunk(BaseModel):
    """Deterministic current-version chunk prepared for Assistant PostgreSQL."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    ordinal: int = Field(ge=0, le=65_535)
    content: str = Field(min_length=1, max_length=32_768)
    start_offset: int = Field(ge=0)
    end_offset: int = Field(gt=0)
    start_line: int = Field(gt=0)
    end_line: int = Field(gt=0)
    fingerprint: str = Field(pattern=FINGERPRINT_PATTERN)
    char_count: int = Field(gt=0, le=32_768)
    byte_count: int = Field(gt=0, le=65_536)

    @model_validator(mode="after")
    def validate_bounds(self) -> "KnowledgeChunk":
        if self.end_offset <= self.start_offset:
            raise ValueError("chunk end_offset must follow start_offset")
        if self.end_line < self.start_line:
            raise ValueError("chunk end_line must not precede start_line")
        if self.char_count != len(self.content):
            raise ValueError("char_count must describe chunk content")
        if self.byte_count != len(self.content.encode("utf-8")):
            raise ValueError("byte_count must describe UTF-8 chunk content")
        return self


class KnowledgeScanMetrics(BaseModel):
    """Browser-safe ingestion diagnostics with no paths or document contents."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    documents_seen: int = Field(ge=0)
    documents_indexed: int = Field(ge=0)
    documents_unchanged: int = Field(ge=0)
    documents_retired: int = Field(ge=0)
    errors: int = Field(ge=0)
    chunks: int = Field(ge=0)
    duration_ms: int = Field(ge=0)


class KnowledgeScanResult(BaseModel):
    """Sanitized result of one incremental knowledge scan."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    metrics: KnowledgeScanMetrics
    issue_codes: tuple[str, ...] = Field(default=(), max_length=256)
    complete: bool


class KnowledgeRef(BaseModel):
    """Opaque logical pointer bound to one current document chunk version."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    document_uuid: UUID
    chunk_uuid: UUID
    provider_id: str = Field(pattern=LOGICAL_ID_PATTERN, max_length=128)
    document_id: str = Field(min_length=1, max_length=1024)
    document_fingerprint: str = Field(pattern=FINGERPRINT_PATTERN)
    chunk_fingerprint: str = Field(pattern=FINGERPRINT_PATTERN)
    ordinal: int = Field(ge=0, le=65_535)

    @field_validator("document_id")
    @classmethod
    def validate_document_id(cls, value: str) -> str:
        return KnowledgeDocument.validate_document_id(value)


class KnowledgeSearchRequest(BaseModel):
    """Bounded lexical query with only persisted allowlisted filters."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    query: str = Field(min_length=1, max_length=256)
    provider_id: str | None = Field(default=None, pattern=LOGICAL_ID_PATTERN, max_length=128)
    locale: str | None = Field(default=None, pattern=LOCALE_PATTERN, max_length=64)
    top_k: int = Field(default=5, gt=0, le=20)

    @field_validator("query")
    @classmethod
    def validate_query(cls, value: str) -> str:
        if value != value.strip() or "\0" in value:
            raise ValueError("knowledge query must be normalized text")
        return value


class KnowledgeSearchCandidate(BaseModel):
    """Lightweight untrusted match; it is not checked Evidence."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    position: int = Field(gt=0, le=20)
    title: str = Field(min_length=1, max_length=512)
    provider_id: str = Field(pattern=LOGICAL_ID_PATTERN, max_length=128)
    document_id: str = Field(min_length=1, max_length=1024)
    locale: str | None = Field(default=None, pattern=LOCALE_PATTERN, max_length=64)
    media_type: KnowledgeMediaType
    snippet: str = Field(min_length=1, max_length=512)
    ref: KnowledgeRef

    @model_validator(mode="after")
    def validate_identity(self) -> "KnowledgeSearchCandidate":
        KnowledgeDocument.validate_document_id(self.document_id)
        if self.ref.provider_id != self.provider_id or self.ref.document_id != self.document_id:
            raise ValueError("candidate identity must match its ref")
        return self


class KnowledgeSearchResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    candidates: tuple[KnowledgeSearchCandidate, ...] = Field(max_length=20)
    truncated: bool


class KnowledgeReadExcerptRequest(BaseModel):
    """Read only a fingerprinted ref previously emitted by search."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    ref: KnowledgeRef
    max_lines: int = Field(default=40, gt=0, le=80)
    max_chars: int = Field(default=4_000, ge=128, le=8_000)
    max_bytes: int = Field(default=8_000, ge=256, le=16_000)


class KnowledgeExcerptLine(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    number: int = Field(gt=0)
    text: str = Field(max_length=8_000)


class KnowledgeStoredChunk(BaseModel):
    """Internal provider-neutral row returned by the retrieval store."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    ref: KnowledgeRef
    title: str = Field(min_length=1, max_length=512)
    locale: str | None = Field(default=None, pattern=LOCALE_PATTERN, max_length=64)
    media_type: KnowledgeMediaType
    content: str = Field(min_length=1, max_length=32_768)
    start_line: int = Field(gt=0)
    end_line: int = Field(gt=0)
    observed_at: datetime


class KnowledgeExcerpt(BaseModel):
    """Bounded current excerpt plus separately ledgered checked Evidence."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    ref: KnowledgeRef
    title: str = Field(min_length=1, max_length=512)
    provider_id: str = Field(pattern=LOGICAL_ID_PATTERN, max_length=128)
    document_id: str = Field(min_length=1, max_length=1024)
    locale: str | None = Field(default=None, pattern=LOCALE_PATTERN, max_length=64)
    media_type: KnowledgeMediaType
    lines: tuple[KnowledgeExcerptLine, ...] = Field(min_length=1, max_length=80)
    truncated: bool
    evidence: Evidence

    @model_validator(mode="after")
    def validate_identity(self) -> "KnowledgeExcerpt":
        KnowledgeDocument.validate_document_id(self.document_id)
        if self.ref.provider_id != self.provider_id or self.ref.document_id != self.document_id:
            raise ValueError("excerpt identity must match its ref")
        return self
