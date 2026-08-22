"""Bounded systemd journal provider with fixed command construction."""

from __future__ import annotations

import asyncio
import hashlib
import re
import subprocess
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, tzinfo
from enum import StrEnum
from typing import Any, Protocol, cast
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
from odoo_ai.logs.common import (
    LogProviderError,
    LogRedactor,
    context_indexes,
    expand_traceback_indexes,
    line_in_window,
    parse_log_lines,
)
from odoo_ai.logs.tracebacks import TracebackRegistry

JOURNAL_UNIT_ENV = "ODOO_AI_JOURNAL_UNIT"
_UNIT = re.compile(r"^(?!-)[A-Za-z0-9_.@:-]{1,247}\.service$")


class JournalUnitOrigin(StrEnum):
    OVERRIDE = "override"
    RUNTIME = "runtime"
    SUPERVISOR = "supervisor"
    CONFIG = "config"
    HINT = "hint"


@dataclass(frozen=True, slots=True)
class JournalUnitSelection:
    override: tuple[str, ...] = ()
    runtime: tuple[str, ...] = ()
    supervisor: tuple[str, ...] = ()
    config: tuple[str, ...] = ()
    hints: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ResolvedJournalUnit:
    unit: str
    origin: JournalUnitOrigin


def journal_unit_override_from_env(environment: Mapping[str, str]) -> tuple[str, ...]:
    value = environment.get(JOURNAL_UNIT_ENV, "")
    return (value,) if value else ()


def resolve_journal_unit(selection: JournalUnitSelection) -> ResolvedJournalUnit | None:
    """Resolve one validated unit using deployment precedence, rejecting ambiguity."""

    tiers = (
        (JournalUnitOrigin.OVERRIDE, selection.override),
        (JournalUnitOrigin.RUNTIME, selection.runtime),
        (JournalUnitOrigin.SUPERVISOR, selection.supervisor),
        (JournalUnitOrigin.CONFIG, selection.config),
        (JournalUnitOrigin.HINT, selection.hints),
    )
    for origin, candidates in tiers:
        unique = tuple(dict.fromkeys(candidates))
        if not unique:
            continue
        if len(unique) != 1 or not _UNIT.fullmatch(unique[0]):
            raise LogProviderError("journal_unit_invalid_or_ambiguous")
        return ResolvedJournalUnit(unique[0], origin)
    return None


@dataclass(frozen=True, slots=True)
class JournalCommandResult:
    returncode: int
    stdout: bytes
    stderr: bytes


class JournalRunner(Protocol):
    def run(
        self, argv: tuple[str, ...], *, timeout: float, max_bytes: int
    ) -> JournalCommandResult: ...


class SubprocessJournalRunner:
    """Run one server-built command without a shell or caller-controlled options."""

    def run(self, argv: tuple[str, ...], *, timeout: float, max_bytes: int) -> JournalCommandResult:
        try:
            completed = subprocess.run(  # noqa: S603 - argv is fixed and validated
                argv,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                timeout=timeout,
                check=False,
                shell=False,
            )
        except subprocess.TimeoutExpired:
            raise LogProviderError("journal_timeout") from None
        return JournalCommandResult(
            returncode=completed.returncode,
            stdout=completed.stdout[: max_bytes + 1],
            stderr=completed.stderr[:4096],
        )


@dataclass(frozen=True, slots=True)
class JournalLogLimits:
    max_output_bytes: int = 65_536
    max_fetch_bytes: int = 2 * 1024 * 1024
    max_fetch_lines: int = 1000
    max_seconds: float = 2.0
    context_lines: int = 2
    default_lookback: timedelta = timedelta(minutes=15)

    def __post_init__(self) -> None:
        if (
            type(self.max_output_bytes) is not int
            or not 1 <= self.max_output_bytes <= 65_536
            or type(self.max_fetch_bytes) is not int
            or self.max_fetch_bytes < self.max_output_bytes
            or type(self.max_fetch_lines) is not int
            or not 1 <= self.max_fetch_lines <= 10_000
            or not isinstance(self.max_seconds, (int, float))
            or self.max_seconds <= 0
            or type(self.context_lines) is not int
            or not 0 <= self.context_lines <= 20
            or self.default_lookback <= timedelta(0)
            or self.default_lookback > timedelta(days=1)
        ):
            raise ValueError("journal log limits are invalid")


class JournalLogProvider:
    """Search a resolved journal unit with bounded server-owned arguments."""

    def __init__(
        self,
        *,
        resolved: ResolvedJournalUnit,
        executable: str = "/usr/bin/journalctl",
        runner: JournalRunner | None = None,
        limits: JournalLogLimits | None = None,
        redactor: LogRedactor | None = None,
        default_timezone: tzinfo = UTC,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if not _UNIT.fullmatch(resolved.unit):
            raise LogProviderError("journal_unit_invalid_or_ambiguous")
        if not executable.startswith("/") or any(character in executable for character in "\r\n"):
            raise ValueError("journal executable must be an absolute server path")
        self._resolved = resolved
        self._executable = executable
        self._runner = runner or SubprocessJournalRunner()
        self._limits = limits or JournalLogLimits()
        self._redactor = redactor or LogRedactor()
        self._default_timezone = default_timezone
        self._now = now
        self._clock = clock
        self._tracebacks = TracebackRegistry(provider="journal", redactor=self._redactor)

    async def search(self, request: LogSearchRequest) -> list[LogEvidence]:
        return await asyncio.to_thread(self._search_sync, request)

    async def read_traceback(self, fingerprint: str, *, max_bytes: int) -> LogEvidence | None:
        return self._tracebacks.read(fingerprint, max_bytes=max_bytes)

    def _search_sync(self, request: LogSearchRequest) -> list[LogEvidence]:
        if request.max_bytes > self._limits.max_output_bytes:
            raise LogProviderError("log_byte_cap_exceeded")
        until = request.to_ts or self._aware_now()
        since = request.from_ts or until - self._limits.default_lookback
        argv = (
            self._executable,
            "--no-pager",
            "--quiet",
            "--output=short-iso-precise",
            "--unit",
            self._resolved.unit,
            "--since",
            _journal_time(since),
            "--until",
            _journal_time(until),
            "--lines",
            str(self._limits.max_fetch_lines),
        )
        try:
            command = self._runner.run(
                argv,
                timeout=self._limits.max_seconds,
                max_bytes=self._limits.max_fetch_bytes,
            )
        except FileNotFoundError:
            raise LogProviderError("journal_not_found") from None
        except PermissionError:
            raise LogProviderError("journal_no_permission") from None
        except subprocess.TimeoutExpired:
            raise LogProviderError("journal_timeout") from None
        if command.returncode:
            stderr = command.stderr.decode("utf-8", errors="replace").casefold()
            if "permission" in stderr or "access denied" in stderr:
                raise LogProviderError("journal_no_permission")
            if "no entries" in stderr or "not found" in stderr:
                return []
            raise LogProviderError("journal_read_error")
        fetch_truncated = len(command.stdout) > self._limits.max_fetch_bytes
        content = command.stdout[: self._limits.max_fetch_bytes]
        raw_lines = content.decode("utf-8", errors="replace").splitlines()
        lines = parse_log_lines(raw_lines, self._default_timezone)
        terms = tuple(term.casefold() for term in request.terms)
        started = self._clock()
        matches: list[int] = []
        timed_out = False
        for index, line in enumerate(lines):
            if index % 256 == 0 and self._clock() - started > self._limits.max_seconds:
                timed_out = True
                break
            if not line_in_window(line.timestamp, request):
                continue
            if terms and not any(term in line.text.casefold() for term in terms):
                continue
            matches.append(index)
        if not matches:
            return []
        selected = context_indexes(matches, len(lines), context=self._limits.context_lines)
        selected = expand_traceback_indexes(raw_lines, selected)
        reasons: list[str] = []
        if fetch_truncated:
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
        timestamps = [
            line.timestamp for index, _ in rendered if (line := lines[index]).timestamp is not None
        ]
        matched_terms = tuple(
            request.terms[position]
            for position, term in enumerate(terms)
            if any(term in lines[index].text.casefold() for index in matches)
        )
        reference = (
            "sha256:"
            + hashlib.sha256(
                f"{self._resolved.unit}:{since.isoformat()}:{until.isoformat()}:{excerpt}".encode()
            ).hexdigest()
        )
        pointer = LogPointer(provider="journal", reference=reference)
        evidence = Evidence(
            evidence_id=UUID(reference.removeprefix("sha256:")[:32]),
            kind=EvidenceKind.LOG,
            status=EvidenceStatus.CHECKED,
            title="Bounded Odoo journal excerpt",
            summary="Redacted on-demand log evidence from a resolved provider.",
            payload=cast(
                dict[str, Any],
                {
                    "provider": "journal",
                    "excerpt": excerpt,
                    "trust": "untrusted_log",
                    "truncated": bool(reasons),
                    "truncation_reasons": reasons,
                },
            ),
            pointer=pointer.model_dump(mode="json"),
            observed_at=max(timestamps) if timestamps else None,
            sensitivity=EvidenceSensitivity.TECHNICAL,
            fingerprint="sha256:" + hashlib.sha256(excerpt.encode()).hexdigest(),
        )
        result = LogEvidence(
            provider="journal",
            timestamp_range=TimestampRange(
                from_ts=min(timestamps) if timestamps else None,
                to_ts=max(timestamps) if timestamps else None,
            ),
            excerpt=excerpt,
            correlation=(
                LogCorrelation.DIRECT if request.terms else LogCorrelation.TEMPORAL_INFERENCE
            ),
            pointer=pointer,
            truncated=bool(reasons),
            truncation_reasons=tuple(dict.fromkeys(reasons)),
            timestamp_parse_complete=not any(
                lines[index].timestamp_invalid for index, _ in rendered
            ),
            matched_terms=matched_terms,
            line_count=len(rendered),
            byte_count=len(excerpt.encode()),
            evidence=evidence,
        )
        return self._tracebacks.index(result)

    def _aware_now(self) -> datetime:
        value = self._now()
        if value.tzinfo is None:
            raise LogProviderError("journal_clock_invalid")
        return value


def _journal_time(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="microseconds")
