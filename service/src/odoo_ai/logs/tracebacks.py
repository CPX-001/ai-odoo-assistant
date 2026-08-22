"""Deterministic traceback extraction, grouping, and bounded lookup."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import PurePath
from typing import Any, cast
from uuid import UUID

from odoo_ai.contracts import Evidence, LogEvidence, LogPointer
from odoo_ai.logs.common import LogProviderError, LogRedactor, strip_log_prefix

_START = "Traceback (most recent call last):"
_FRAME = re.compile(r'^\s*File "(?P<path>[^"]+)", line \d+, in (?P<function>.+)$')
_EXCEPTION = re.compile(
    r"^(?P<type>[A-Za-z_][A-Za-z0-9_.]*(?:Error|Exception|Warning|Interrupt))"
    r"(?::\s*(?P<message>.*))?$"
)
_FINGERPRINT = re.compile(r"^sha256:[0-9a-f]{64}$")
_UUID = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-"
    r"[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}\b"
)
_ADDRESS = re.compile(r"\b0x[0-9a-fA-F]+\b")
_NUMBER = re.compile(r"\b\d+\b")
_TIMESTAMPED = re.compile(r"^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}")


@dataclass(frozen=True, slots=True)
class TracebackBlock:
    excerpt: str
    fingerprint: str


def extract_tracebacks(excerpt: str) -> tuple[TracebackBlock, ...]:
    """Extract complete Python tracebacks and calculate stable fingerprints."""

    lines = excerpt.splitlines()
    result: list[TracebackBlock] = []
    index = 0
    while index < len(lines):
        if _START not in lines[index]:
            index += 1
            continue
        start = index
        index += 1
        exception_index: int | None = None
        while index < len(lines):
            if index > start + 1 and _START in lines[index]:
                break
            candidate = strip_log_prefix(lines[index])
            if _EXCEPTION.match(candidate):
                exception_index = index
                index += 1
                break
            if index > start + 1 and _TIMESTAMPED.match(lines[index]):
                break
            index += 1
        if exception_index is None:
            continue
        block_lines = lines[start : exception_index + 1]
        block = "\n".join(block_lines)
        result.append(TracebackBlock(block, traceback_fingerprint(block_lines)))
    return tuple(result)


def traceback_fingerprint(lines: list[str]) -> str:
    frames: list[str] = []
    exception_type = "unknown"
    message = ""
    for line in lines:
        normalized = strip_log_prefix(line)
        frame = _FRAME.match(normalized)
        if frame:
            frames.append(f"{PurePath(frame.group('path')).name}:{frame.group('function').strip()}")
        exception = _EXCEPTION.match(normalized)
        if exception:
            exception_type = exception.group("type")
            message = _normalize_message(exception.group("message") or "")
    canonical = "|".join((exception_type, message, *frames))
    return "sha256:" + hashlib.sha256(canonical.encode()).hexdigest()


class TracebackRegistry:
    """In-memory allowlist of redacted traceback references emitted by search."""

    def __init__(self, *, provider: str, redactor: LogRedactor) -> None:
        self._provider = provider
        self._redactor = redactor
        self._entries: dict[str, LogEvidence] = {}

    def index(self, result: LogEvidence) -> list[LogEvidence]:
        blocks = extract_tracebacks(result.excerpt)
        if not blocks:
            return [result]
        grouped: dict[str, list[TracebackBlock]] = {}
        for block in blocks:
            grouped.setdefault(block.fingerprint, []).append(block)
        indexed: list[LogEvidence] = []
        for fingerprint, occurrences in grouped.items():
            excerpt = self._redactor.redact(occurrences[0].excerpt)
            pointer = LogPointer(provider=self._provider, reference=fingerprint)
            evidence = _traceback_evidence(result, excerpt, pointer, len(occurrences))
            entry = result.model_copy(
                update={
                    "excerpt": excerpt,
                    "traceback_fingerprint": fingerprint,
                    "pointer": pointer,
                    "line_count": len(excerpt.splitlines()),
                    "byte_count": len(excerpt.encode()),
                    "occurrence_count": len(occurrences),
                    "evidence": evidence,
                }
            )
            self._entries[fingerprint] = entry
            indexed.append(entry)
        return indexed

    def read(self, fingerprint: str, *, max_bytes: int) -> LogEvidence | None:
        if not _FINGERPRINT.fullmatch(fingerprint):
            raise LogProviderError("traceback_reference_invalid")
        if type(max_bytes) is not int or not 1 <= max_bytes <= 65_536:
            raise LogProviderError("traceback_byte_cap_invalid")
        entry = self._entries.get(fingerprint)
        if entry is None:
            raise LogProviderError("traceback_reference_unknown")
        excerpt = self._redactor.redact(entry.excerpt)
        encoded = excerpt.encode()
        truncated = len(encoded) > max_bytes
        if truncated:
            excerpt = encoded[:max_bytes].decode("utf-8", errors="ignore")
            if not excerpt:
                raise LogProviderError("traceback_byte_cap_too_small")
        extra_reasons = ("byte_cap",) if truncated else ()
        reasons = tuple(dict.fromkeys((*entry.truncation_reasons, *extra_reasons)))
        evidence = entry.evidence
        if evidence is not None:
            payload = dict(evidence.payload)
            payload["excerpt"] = excerpt
            payload["truncated"] = entry.truncated or truncated
            payload["truncation_reasons"] = list(reasons)
            evidence = evidence.model_copy(update={"payload": payload})
        return entry.model_copy(
            update={
                "excerpt": excerpt,
                "line_count": len(excerpt.splitlines()),
                "byte_count": len(excerpt.encode()),
                "truncated": entry.truncated or truncated,
                "truncation_reasons": reasons,
                "evidence": evidence,
            }
        )


def _normalize_message(message: str) -> str:
    value = _UUID.sub("<uuid>", message.casefold())
    value = _ADDRESS.sub("<address>", value)
    value = _NUMBER.sub("<number>", value)
    return " ".join(value.split())


def _traceback_evidence(
    source: LogEvidence,
    excerpt: str,
    pointer: LogPointer,
    occurrence_count: int,
) -> Evidence | None:
    if source.evidence is None:
        return None
    payload = dict(source.evidence.payload)
    payload.update(
        cast(
            dict[str, Any],
            {
                "excerpt": excerpt,
                "traceback_fingerprint": pointer.reference,
                "occurrence_count": occurrence_count,
            },
        )
    )
    return source.evidence.model_copy(
        update={
            "evidence_id": UUID(pointer.reference.removeprefix("sha256:")[:32]),
            "title": "Grouped Odoo traceback evidence",
            "summary": "Redacted traceback grouped by a deterministic fingerprint.",
            "payload": payload,
            "pointer": pointer.model_dump(mode="json"),
            "fingerprint": pointer.reference,
        }
    )
