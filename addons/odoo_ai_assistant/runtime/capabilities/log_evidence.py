"""Bounded, correlated and redacted Evidence from the configured Odoo log."""

from __future__ import annotations

import hashlib
import os
import re
import stat
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from .contracts import CapabilityContext, CapabilityError, JsonValue
from .evidence import (
    EvidenceAccessScope,
    EvidenceFreshness,
    EvidenceItem,
    EvidenceKind,
    EvidenceLocator,
    EvidenceProvider,
    EvidenceRef,
    EvidenceSearchRequest,
    EvidenceSearchResult,
    EvidenceTrust,
    redact_secrets,
)

PROVIDER_ID = "assistant.odoo_log"
SOURCE_ID = "odoo.configured_log"
MAX_SCAN_BYTES = 4 * 1024 * 1024
MAX_EXCERPT_LINES = 160
MAX_RESULTS = 6
_TOKEN_RE = re.compile(r"[A-Za-zÀ-ÿ_][A-Za-zÀ-ÿ0-9_.:-]{2,}")
_TRACEBACK = "Traceback (most recent call last):"
_SECRET_ASSIGNMENT = re.compile(
    r"(?i)\b(password|passwd|pwd|secret|token|api[_-]?key|authorization)(\s*[:=]\s*)(?:\"[^\"\r\n]*\"|'[^'\r\n]*'|[^\s,;]+)"
)
_URL_CREDENTIAL = re.compile(r"(?i)\b([a-z][a-z0-9+.-]*://[^\s:/@]+:)[^\s/@]+(@)")

LogPathResolver = Callable[[CapabilityContext], Path]


def _is_technical(context: CapabilityContext) -> bool:
    user = getattr(getattr(context, "env", None), "user", None)
    try:
        return bool(user and user.has_group("base.group_system"))
    except Exception:  # noqa: BLE001 - technical Evidence fails closed
        return False


def _configured_log_path(_context: CapabilityContext) -> Path:
    try:
        from odoo.tools import config

        raw = config.get("logfile")
    except Exception as exc:
        raise CapabilityError("log_evidence_config_unavailable") from exc
    if not isinstance(raw, str) or not raw.strip():
        raise CapabilityError("log_evidence_not_configured")
    return Path(raw).resolve(strict=True)


def _redact(text: str) -> str:
    text = redact_secrets(text)
    text = _SECRET_ASSIGNMENT.sub(lambda match: f"{match.group(1)}{match.group(2)}[REDACTED_SECRET]", text)
    return _URL_CREDENTIAL.sub(
        lambda match: f"{match.group(1)}[REDACTED_SECRET]{match.group(2)}", text
    )


def _read_tail(path: Path) -> tuple[bytes, int, os.stat_result]:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except PermissionError:
        raise CapabilityError("log_evidence_access_denied") from None
    except FileNotFoundError:
        raise CapabilityError("log_evidence_missing") from None
    except OSError:
        raise CapabilityError("log_evidence_open_failed") from None
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise CapabilityError("log_evidence_not_regular")
        offset = max(0, metadata.st_size - MAX_SCAN_BYTES)
        os.lseek(descriptor, offset, os.SEEK_SET)
        content = os.read(descriptor, MAX_SCAN_BYTES)
        if offset and content:
            skipped, separator, remaining = content.partition(b"\n")
            del skipped
            if separator:
                offset += len(content) - len(remaining)
                content = remaining
        return content, offset, metadata
    finally:
        os.close(descriptor)


def _terms(request: EvidenceSearchRequest) -> tuple[str, ...]:
    ignored = {
        "analiza",
        "error",
        "errores",
        "fallo",
        "odoo",
        "traceback",
        "ultimo",
        "último",
    }
    explicit = [token.casefold() for token in _TOKEN_RE.findall(request.query)]
    metadata = request.metadata
    for key in ("model", "record", "action", "component"):
        value = metadata.get(key)
        if isinstance(value, str):
            explicit.extend(token.casefold() for token in _TOKEN_RE.findall(value))
        elif isinstance(value, int):
            explicit.append(str(value))
    return tuple(dict.fromkeys(token for token in explicit if token not in ignored))[:12]


def _blocks(lines: list[str], matches: list[int]) -> list[tuple[int, int, int]]:
    result: list[tuple[int, int, int]] = []
    for match in matches:
        start = max(0, match - 3)
        traceback_starts = [
            index
            for index in range(max(0, match - 120), match + 1)
            if _TRACEBACK in lines[index]
        ]
        if traceback_starts:
            start = traceback_starts[-1]
        end = min(len(lines), match + 4)
        if traceback_starts:
            end = min(len(lines), start + MAX_EXCERPT_LINES)
            for index in range(match + 1, end):
                if lines[index].startswith(("202", "INFO ", "WARNING ")):
                    end = index
                    break
        result.append((start, max(start + 1, end), match))
    deduplicated: list[tuple[int, int, int]] = []
    for item in sorted(result, key=lambda value: value[2], reverse=True):
        if not any(item[0] >= existing[0] and item[1] <= existing[1] for existing in deduplicated):
            deduplicated.append(item)
    return deduplicated[:MAX_RESULTS]


def _make_ref(
    context: CapabilityContext,
    *,
    start_byte: int,
    end_byte: int,
    line_start: int,
    line_end: int,
    fingerprint: str,
    file_identity: str,
    freshness: EvidenceFreshness = EvidenceFreshness.CURRENT,
    score: float = 0.0,
) -> EvidenceRef:
    identity = hashlib.sha256(
        f"{file_identity}:{start_byte}:{end_byte}".encode()
    ).hexdigest()[:24]
    return EvidenceRef(
        evidence_id=f"log:{identity}",
        kind=EvidenceKind.LOG,
        provider_id=PROVIDER_ID,
        locator=EvidenceLocator(
            provider_id=PROVIDER_ID,
            source_id=SOURCE_ID,
            key=f"excerpt-{identity}",
            parameters={
                "start_byte": start_byte,
                "end_byte": end_byte,
                "line_start": line_start,
                "line_end": line_end,
                "file_identity": file_identity,
            },
        ),
        title="Correlated Odoo log excerpt",
        provenance="Configured Odoo log, bounded correlated excerpt",
        fingerprint=fingerprint,
        captured_at=datetime.now(UTC),
        freshness=freshness,
        trust=EvidenceTrust.UNTRUSTED,
        access_scope=EvidenceAccessScope.bind(
            context, group_xmlids=("base.group_system",)
        ),
        citation={
            "source_type": "odoo_log",
            "line_start": line_start,
            "line_end": line_end,
        },
        score=score,
        metadata={
            "correlation": "term_and_context",
            "logical_locator_only": True,
            "redacted": True,
            "technical_only": True,
        },
    )


def build_odoo_log_evidence_provider(
    *, path_resolver: LogPathResolver | None = None
) -> EvidenceProvider:
    resolve_path = path_resolver or _configured_log_path

    def search(
        context: CapabilityContext, request: EvidenceSearchRequest
    ) -> EvidenceSearchResult:
        if request.kinds and EvidenceKind.LOG not in request.kinds:
            return EvidenceSearchResult(provider_id=PROVIDER_ID, refs=())
        terms = _terms(request)
        if not terms:
            return EvidenceSearchResult(provider_id=PROVIDER_ID, refs=())
        content, offset, metadata = _read_tail(resolve_path(context))
        decoded = content.decode("utf-8", errors="replace")
        raw_lines = decoded.splitlines(keepends=True)
        lines = [line.rstrip("\r\n") for line in raw_lines]
        matches = [
            index
            for index, line in enumerate(lines)
            if any(term in line.casefold() for term in terms)
        ]
        starts: list[int] = []
        cursor = offset
        for line in raw_lines:
            starts.append(cursor)
            cursor += len(line.encode("utf-8", errors="replace"))
        starts.append(cursor)
        file_identity = f"{metadata.st_dev}:{metadata.st_ino}"
        refs = []
        for start, end, match in _blocks(lines, matches):
            excerpt = _redact("\n".join(lines[start:end]))
            score = float(
                sum(excerpt.casefold().count(term) for term in terms)
                + (2 if _TRACEBACK in excerpt else 0)
            )
            refs.append(
                _make_ref(
                    context,
                    start_byte=starts[start],
                    end_byte=starts[end],
                    line_start=start + 1,
                    line_end=end,
                    fingerprint=hashlib.sha256(excerpt.encode()).hexdigest(),
                    file_identity=file_identity,
                    score=score,
                )
            )
        refs.sort(key=lambda item: (-(item.score or 0.0), item.evidence_id))
        return EvidenceSearchResult(
            provider_id=PROVIDER_ID,
            refs=tuple(refs[: min(request.max_results, MAX_RESULTS)]),
            truncated=len(refs) > min(request.max_results, MAX_RESULTS),
        )

    def fetch(context: CapabilityContext, requested: EvidenceRef) -> EvidenceItem:
        if not requested.access_scope.allows(context):
            raise CapabilityError("evidence_access_denied")
        path = resolve_path(context)
        start_raw = requested.locator.parameters.get("start_byte")
        end_raw = requested.locator.parameters.get("end_byte")
        start_byte = int(start_raw) if isinstance(start_raw, int) else -1
        end_byte = int(end_raw) if isinstance(end_raw, int) else -1
        expected_identity = str(requested.locator.parameters.get("file_identity") or "")
        if start_byte < 0 or end_byte <= start_byte or end_byte - start_byte > 128 * 1024:
            raise CapabilityError("log_evidence_locator_invalid")
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(path, flags)
            metadata = os.fstat(descriptor)
            current_identity = f"{metadata.st_dev}:{metadata.st_ino}"
            os.lseek(descriptor, start_byte, os.SEEK_SET)
            raw = os.read(descriptor, end_byte - start_byte)
        except (FileNotFoundError, PermissionError, OSError):
            raise CapabilityError("log_evidence_read_failed") from None
        finally:
            if "descriptor" in locals():
                os.close(descriptor)
        excerpt = _redact(raw.decode("utf-8", errors="replace").strip())
        fingerprint = hashlib.sha256(excerpt.encode()).hexdigest()
        freshness = (
            EvidenceFreshness.CURRENT
            if current_identity == expected_identity and fingerprint == requested.fingerprint
            else EvidenceFreshness.STALE
        )
        ref = _make_ref(
            context,
            start_byte=start_byte,
            end_byte=end_byte,
            line_start=int(requested.locator.parameters.get("line_start") or 1),
            line_end=int(requested.locator.parameters.get("line_end") or 1),
            fingerprint=fingerprint,
            file_identity=expected_identity,
            freshness=freshness,
            score=requested.score or 0.0,
        )
        data: dict[str, JsonValue] = {
            "correlation": "term_and_context",
            "redacted": True,
            "line_start": requested.locator.parameters.get("line_start"),
            "line_end": requested.locator.parameters.get("line_end"),
        }
        if freshness is EvidenceFreshness.STALE:
            data["requested_fingerprint"] = requested.fingerprint
            data["current_fingerprint"] = fingerprint
        return EvidenceItem(ref=ref, excerpt=excerpt, data=data)

    return EvidenceProvider(
        provider_id=PROVIDER_ID,
        version="1",
        kinds=(EvidenceKind.LOG,),
        search=search,
        fetch=fetch,
        guard=_is_technical,
        optional=True,
        max_results=MAX_RESULTS,
        max_excerpt_bytes=16 * 1024,
        max_total_bytes=64 * 1024,
        metadata={
            "namespace_owner": "core",
            "configured_log_only": True,
            "logical_locator_only": True,
            "redacted": True,
            "technical_only": True,
        },
    )


__all__ = ["PROVIDER_ID", "SOURCE_ID", "build_odoo_log_evidence_provider"]
