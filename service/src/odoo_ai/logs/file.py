"""On-demand, bounded FileLogProvider."""

from __future__ import annotations

import asyncio
import hashlib
import os
import re
import stat
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, tzinfo
from typing import Any, cast
from uuid import UUID

from odoo_ai.contracts import (
    Evidence,
    EvidenceKind,
    EvidenceSensitivity,
    EvidenceStatus,
    LogCorrelation,
    LogEvidence,
    LogPointer,
    LogSearchRequest,
    TimestampRange,
)
from odoo_ai.logs.common import LogRedactor
from odoo_ai.logs.resolution import ResolvedLogFile

_TIMESTAMP = re.compile(
    r"^(?P<value>\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:[.,]\d{1,6})?"
    r"(?:Z|[+-]\d{2}:?\d{2})?)"
)
_DATE_LIKE = re.compile(r"^\d{4}-\d{2}-\d{2}")


class LogProviderError(RuntimeError):
    """Sanitized provider failure that never includes a log path."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class FileLogLimits:
    max_output_bytes: int = 65_536
    max_scan_bytes: int = 8 * 1024 * 1024
    max_seconds: float = 2.0
    context_lines: int = 2

    def __post_init__(self) -> None:
        if (
            type(self.max_output_bytes) is not int
            or not 1 <= self.max_output_bytes <= 65_536
            or type(self.max_scan_bytes) is not int
            or self.max_scan_bytes < self.max_output_bytes
            or not isinstance(self.max_seconds, (int, float))
            or self.max_seconds <= 0
            or type(self.context_lines) is not int
            or not 0 <= self.context_lines <= 20
        ):
            raise ValueError("file log limits are invalid")


@dataclass(frozen=True, slots=True)
class _LogLine:
    text: str
    timestamp: datetime | None
    timestamp_invalid: bool


@dataclass(frozen=True, slots=True)
class _TailRead:
    content: bytes
    file_truncated: bool
    identity: str


class FileLogProvider:
    """Search one resolved regular file without ingesting or exposing its path."""

    def __init__(
        self,
        *,
        resolved: ResolvedLogFile,
        limits: FileLogLimits | None = None,
        redactor: LogRedactor | None = None,
        default_timezone: tzinfo = UTC,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._resolved = resolved
        self._limits = limits or FileLogLimits()
        self._redactor = redactor or LogRedactor()
        self._default_timezone = default_timezone
        self._clock = clock

    async def search(self, request: LogSearchRequest) -> list[LogEvidence]:
        return await asyncio.to_thread(self._search_sync, request)

    async def read_traceback(
        self, fingerprint: str, *, max_bytes: int
    ) -> LogEvidence | None:
        del fingerprint, max_bytes
        return None

    def _search_sync(self, request: LogSearchRequest) -> list[LogEvidence]:
        if request.max_bytes > self._limits.max_output_bytes:
            raise LogProviderError("log_byte_cap_exceeded")
        if not request.terms and request.from_ts is None and request.to_ts is None:
            raise LogProviderError("log_filter_required")
        started = self._clock()
        tail = self._read_tail()
        raw_lines = tail.content.decode("utf-8", errors="replace").splitlines()
        lines = _parse_lines(raw_lines, self._default_timezone)
        terms = tuple(term.casefold() for term in request.terms)
        matches: list[int] = []
        timed_out = False
        for index, line in enumerate(lines):
            if index % 256 == 0 and self._clock() - started > self._limits.max_seconds:
                timed_out = True
                break
            if not _in_window(line.timestamp, request):
                continue
            if terms and not any(term in line.text.casefold() for term in terms):
                continue
            matches.append(index)
        if not matches:
            return []
        selected = _context_indexes(
            matches, len(lines), context=self._limits.context_lines
        )
        reasons: list[str] = []
        if tail.file_truncated:
            reasons.append("scan_byte_cap")
        if timed_out:
            reasons.append("time_cap")
        if len(selected) > request.max_lines:
            selected = selected[: request.max_lines]
            reasons.append("line_cap")
        rendered: list[tuple[int, str]] = []
        byte_count = 0
        for index in selected:
            redacted = self._redactor.redact(lines[index].text)
            addition = len((redacted + "\n").encode())
            if byte_count + addition > request.max_bytes:
                reasons.append("byte_cap")
                break
            rendered.append((index, redacted))
            byte_count += addition
        if not rendered:
            raise LogProviderError("log_byte_cap_too_small")
        excerpt = "\n".join(text for _, text in rendered)
        timestamps: list[datetime] = [
            cast(datetime, lines[index].timestamp)
            for index, _ in rendered
            if lines[index].timestamp is not None
        ]
        parse_complete = not any(
            lines[index].timestamp_invalid for index, _ in rendered
        )
        matched_terms = tuple(
            request.terms[position]
            for position, term in enumerate(terms)
            if any(term in lines[index].text.casefold() for index in matches)
        )
        excerpt_fingerprint = "sha256:" + hashlib.sha256(excerpt.encode()).hexdigest()
        reference = "sha256:" + hashlib.sha256(
            f"{tail.identity}:{rendered[0][0]}:{rendered[-1][0]}".encode()
        ).hexdigest()
        pointer = LogPointer(provider="file", reference=reference)
        timestamp_range = TimestampRange(
            from_ts=min(timestamps) if timestamps else None,
            to_ts=max(timestamps) if timestamps else None,
        )
        evidence = Evidence(
            evidence_id=_evidence_uuid(reference),
            kind=EvidenceKind.LOG,
            status=EvidenceStatus.CHECKED,
            title="Bounded Odoo file log excerpt",
            summary="Redacted on-demand log evidence from a resolved provider.",
            payload=cast(
                dict[str, Any],
                {
                    "provider": "file",
                    "excerpt": excerpt,
                    "trust": "untrusted_log",
                    "truncated": bool(reasons),
                    "truncation_reasons": reasons,
                },
            ),
            pointer=pointer.model_dump(mode="json"),
            observed_at=max(timestamps) if timestamps else None,
            sensitivity=EvidenceSensitivity.TECHNICAL,
            fingerprint=excerpt_fingerprint,
        )
        return [
            LogEvidence(
                provider="file",
                timestamp_range=timestamp_range,
                excerpt=excerpt,
                correlation=(
                    LogCorrelation.DIRECT
                    if request.terms
                    else LogCorrelation.TEMPORAL_INFERENCE
                ),
                pointer=pointer,
                truncated=bool(reasons),
                truncation_reasons=tuple(dict.fromkeys(reasons)),
                timestamp_parse_complete=parse_complete,
                matched_terms=matched_terms,
                line_count=len(rendered),
                byte_count=len(excerpt.encode()),
                evidence=evidence,
            )
        ]

    def _read_tail(self) -> _TailRead:
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            descriptor = os.open(self._resolved.path, flags)
        except PermissionError:
            raise LogProviderError("log_no_permission") from None
        except FileNotFoundError:
            raise LogProviderError("log_not_found") from None
        except OSError:
            raise LogProviderError("log_open_error") from None
        try:
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode):
                raise LogProviderError("log_not_regular")
            offset = max(0, metadata.st_size - self._limits.max_scan_bytes)
            os.lseek(descriptor, offset, os.SEEK_SET)
            content = os.read(descriptor, self._limits.max_scan_bytes + 1)
            if offset and content:
                content = content.partition(b"\n")[2]
            return _TailRead(
                content=content[: self._limits.max_scan_bytes],
                file_truncated=offset > 0 or len(content) > self._limits.max_scan_bytes,
                identity=f"{metadata.st_dev}:{metadata.st_ino}:{metadata.st_size}",
            )
        except OSError:
            raise LogProviderError("log_read_error") from None
        finally:
            os.close(descriptor)


def _parse_lines(raw_lines: list[str], default_timezone: tzinfo) -> list[_LogLine]:
    result: list[_LogLine] = []
    current: datetime | None = None
    for text in raw_lines:
        parsed, invalid = _parse_timestamp(text, default_timezone)
        if parsed is not None:
            current = parsed
        result.append(_LogLine(text=text, timestamp=parsed or current, timestamp_invalid=invalid))
    return result


def _parse_timestamp(text: str, default_timezone: tzinfo) -> tuple[datetime | None, bool]:
    match = _TIMESTAMP.match(text)
    if match is None:
        return None, bool(_DATE_LIKE.match(text))
    value = match.group("value").replace(",", ".")
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    if re.search(r"[+-]\d{4}$", value):
        value = value[:-5] + value[-5:-2] + ":" + value[-2:]
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None, True
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=default_timezone)
    return parsed.astimezone(UTC), False


def _in_window(timestamp: datetime | None, request: LogSearchRequest) -> bool:
    if request.from_ts is None and request.to_ts is None:
        return True
    if timestamp is None:
        return False
    if request.from_ts is not None and timestamp < request.from_ts.astimezone(UTC):
        return False
    return not (
        request.to_ts is not None and timestamp > request.to_ts.astimezone(UTC)
    )


def _context_indexes(matches: list[int], line_count: int, *, context: int) -> list[int]:
    selected: set[int] = set()
    for index in matches:
        selected.update(
            range(max(0, index - context), min(line_count, index + context + 1))
        )
    return sorted(selected)


def _evidence_uuid(reference: str) -> UUID:
    return UUID(reference.removeprefix("sha256:")[:32])
