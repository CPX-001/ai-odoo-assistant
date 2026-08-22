"""Shared bounded log redaction primitives."""

import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, tzinfo
from re import Pattern

from odoo_ai.contracts import LogSearchRequest

_REDACTED = "<redacted>"
_BUILTIN_PATTERNS = (
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{8,}"),
    re.compile(
        r"(?i)\b(password|passwd|pwd|secret|token|api[_-]?key|authorization)"
        r"(\s*[:=]\s*)(?:\"[^\"\r\n]*\"|'[^'\r\n]*'|[^\s,;]+)"
    ),
    re.compile(r"(?i)\b([a-z][a-z0-9+.-]*://[^\s:/@]+:)[^\s/@]+(@)"),
)
_TIMESTAMP = re.compile(
    r"^(?P<value>\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:[.,]\d{1,6})?"
    r"(?:Z|[+-]\d{2}:?\d{2})?)"
)
_DATE_LIKE = re.compile(r"^\d{4}-\d{2}-\d{2}")
_JOURNAL_PREFIX = re.compile(
    r"^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:[.,]\d{1,6})?"
    r"(?:Z|[+-]\d{2}:?\d{2})\s+\S+\s+\S+(?:\[\d+\])?:\s?"
)
_TRACEBACK_START = "Traceback (most recent call last):"
_TRACEBACK_END = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*(?:Error|Exception|Warning|Interrupt)(?::|$)")


class LogProviderError(RuntimeError):
    """Sanitized provider failure with a stable, non-sensitive code."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class ParsedLogLine:
    text: str
    timestamp: datetime | None
    timestamp_invalid: bool


class LogRedactor:
    """Redact known credential shapes and configured literal product secrets."""

    def __init__(
        self,
        *,
        configured_secrets: Iterable[str] = (),
        configured_patterns: Iterable[Pattern[str]] = (),
    ) -> None:
        self._secrets = tuple(
            sorted(
                {value for value in configured_secrets if len(value) >= 8},
                key=len,
                reverse=True,
            )
        )
        self._patterns = tuple(configured_patterns)

    def redact(self, text: str) -> str:
        result = text
        for secret in self._secrets:
            result = result.replace(secret, _REDACTED)
        for pattern in self._patterns:
            result = pattern.sub(_REDACTED, result)
        result = _BUILTIN_PATTERNS[0].sub(f"Bearer {_REDACTED}", result)
        result = _BUILTIN_PATTERNS[1].sub(
            lambda match: f"{match.group(1)}{match.group(2)}{_REDACTED}", result
        )
        return _BUILTIN_PATTERNS[2].sub(
            lambda match: f"{match.group(1)}{_REDACTED}{match.group(2)}", result
        )


def parse_log_lines(raw_lines: list[str], default_timezone: tzinfo) -> list[ParsedLogLine]:
    result: list[ParsedLogLine] = []
    current: datetime | None = None
    for text in raw_lines:
        parsed, invalid = parse_log_timestamp(text, default_timezone)
        if parsed is not None:
            current = parsed
        result.append(
            ParsedLogLine(
                text=text,
                timestamp=parsed or current,
                timestamp_invalid=invalid,
            )
        )
    return result


def parse_log_timestamp(text: str, default_timezone: tzinfo) -> tuple[datetime | None, bool]:
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


def strip_log_prefix(text: str) -> str:
    """Remove the fixed journal prefix while preserving ordinary file log lines."""

    marker = text.find(_TRACEBACK_START)
    if marker >= 0:
        return text[marker:]
    stripped = text.strip()
    prefix = _JOURNAL_PREFIX.match(stripped)
    if prefix is not None:
        return stripped[prefix.end() :].strip()
    return stripped


def line_in_window(timestamp: datetime | None, request: LogSearchRequest) -> bool:
    if request.from_ts is None and request.to_ts is None:
        return True
    if timestamp is None:
        return False
    if request.from_ts is not None and timestamp < request.from_ts.astimezone(UTC):
        return False
    return not (request.to_ts is not None and timestamp > request.to_ts.astimezone(UTC))


def context_indexes(matches: list[int], line_count: int, *, context: int) -> list[int]:
    selected: set[int] = set()
    for index in matches:
        selected.update(range(max(0, index - context), min(line_count, index + context + 1)))
    return sorted(selected)


def expand_traceback_indexes(
    raw_lines: list[str], selected: list[int], *, max_traceback_lines: int = 200
) -> list[int]:
    """Complete nearby Python tracebacks before applying final output caps."""

    expanded = set(selected)
    for start, line in enumerate(raw_lines):
        if _TRACEBACK_START not in line:
            continue
        if not any(start - 1 <= index <= start + 1 for index in expanded):
            continue
        for index in range(start, min(len(raw_lines), start + max_traceback_lines)):
            expanded.add(index)
            candidate = strip_log_prefix(raw_lines[index])
            if index > start and _TRACEBACK_END.match(candidate):
                break
    return sorted(expanded)
