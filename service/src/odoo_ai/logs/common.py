"""Shared bounded log redaction primitives."""

import re
from collections.abc import Iterable

_REDACTED = "<redacted>"
_BUILTIN_PATTERNS = (
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{8,}"),
    re.compile(
        r"(?i)\b(password|passwd|pwd|secret|token|api[_-]?key|authorization)"
        r"(\s*[:=]\s*)(?:\"[^\"\r\n]*\"|'[^'\r\n]*'|[^\s,;]+)"
    ),
    re.compile(r"(?i)\b([a-z][a-z0-9+.-]*://[^\s:/@]+:)[^\s/@]+(@)"),
)


class LogRedactor:
    """Redact known credential shapes and configured literal product secrets."""

    def __init__(self, *, configured_secrets: Iterable[str] = ()) -> None:
        self._secrets = tuple(
            sorted(
                {value for value in configured_secrets if len(value) >= 8},
                key=len,
                reverse=True,
            )
        )

    def redact(self, text: str) -> str:
        result = text
        for secret in self._secrets:
            result = result.replace(secret, _REDACTED)
        result = _BUILTIN_PATTERNS[0].sub(f"Bearer {_REDACTED}", result)
        result = _BUILTIN_PATTERNS[1].sub(
            lambda match: f"{match.group(1)}{match.group(2)}{_REDACTED}", result
        )
        return _BUILTIN_PATTERNS[2].sub(
            lambda match: f"{match.group(1)}{_REDACTED}{match.group(2)}", result
        )
