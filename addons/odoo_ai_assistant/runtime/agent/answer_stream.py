"""Dependency-light extraction of user-facing answer text from Codex structured-output deltas."""

from __future__ import annotations

import json
import re

_MAX_BUFFER = 64 * 1024
_MAX_EMITTED = 16 * 1024
_KIND_RE = re.compile(r'"kind"\s*:\s*"final_answer"')
_ANSWER_RE = re.compile(r'"answer"\s*:\s*"')
_HEX = frozenset("0123456789abcdefABCDEF")
_ESCAPES = frozenset('"\\/bfnrt')


class AnswerStreamError(RuntimeError):
    def __init__(self, code: str = "answer_stream_invalid") -> None:
        super().__init__(code)
        self.code = code


class StructuredFinalAnswerDeltaExtractor:
    """Expose only the decoded ``decision.answer`` string from incremental JSON.

    Codex streams the full structured-output document. This parser never forwards raw JSON,
    plan/tool decisions, arguments, or provider metadata. It waits until ``kind=final_answer`` is
    visible, then emits only newly decoded answer characters.
    """

    def __init__(self) -> None:
        self._buffer = ""
        self._observed = ""
        self._delivered = ""
        self._closed = False

    @property
    def emitted_text(self) -> str:
        return self._delivered

    def feed(self, delta: object) -> tuple[str, ...]:
        if self._closed:
            raise AnswerStreamError("answer_stream_closed")
        if not isinstance(delta, str) or not delta or "\x00" in delta:
            raise AnswerStreamError()
        self._buffer += delta
        if len(self._buffer) > _MAX_BUFFER:
            raise AnswerStreamError("answer_stream_too_large")
        if _KIND_RE.search(self._buffer) is None:
            return ()
        match = _ANSWER_RE.search(self._buffer)
        if match is None:
            return ()
        decoded, closed = _decode_json_string_prefix(self._buffer, match.end())
        if len(decoded) > _MAX_EMITTED:
            raise AnswerStreamError("answer_stream_too_large")
        if not decoded.startswith(self._observed):
            raise AnswerStreamError("answer_stream_non_monotonic")
        self._observed = decoded
        fresh = decoded[len(self._delivered) :]
        if not closed and len(fresh) < 64:
            return ()
        if fresh:
            self._delivered = decoded
        if closed:
            self._closed = True
        return _chunks(fresh)


def _decode_json_string_prefix(buffer: str, start: int) -> tuple[str, bool]:
    raw: list[str] = []
    index = start
    closed = False
    while index < len(buffer):
        character = buffer[index]
        if character == '"':
            closed = True
            break
        if ord(character) < 0x20:
            raise AnswerStreamError()
        if character != "\\":
            raw.append(character)
            index += 1
            continue
        if index + 1 >= len(buffer):
            break
        escape = buffer[index + 1]
        if escape == "u":
            if index + 6 > len(buffer):
                break
            digits = buffer[index + 2 : index + 6]
            if any(digit not in _HEX for digit in digits):
                raise AnswerStreamError()
            raw.append(buffer[index : index + 6])
            index += 6
            continue
        if escape not in _ESCAPES:
            raise AnswerStreamError()
        raw.append(buffer[index : index + 2])
        index += 2

    encoded = "".join(raw)
    try:
        decoded = json.loads(f'"{encoded}"')
    except (TypeError, ValueError):
        raise AnswerStreamError() from None
    if not isinstance(decoded, str):
        raise AnswerStreamError()
    try:
        decoded = decoded.encode("utf-16", "surrogatepass").decode("utf-16")
    except UnicodeDecodeError:
        # A complete high-surrogate escape may arrive before its low surrogate. Hold it back
        # until the next provider delta instead of exposing malformed Unicode.
        if re.search(r"\\u[dD][89AaBb][0-9A-Fa-f]{2}$", encoded):
            encoded = encoded[:-6]
            try:
                decoded = json.loads(f'"{encoded}"')
                decoded = decoded.encode("utf-16", "surrogatepass").decode("utf-16")
            except (TypeError, ValueError, UnicodeDecodeError):
                raise AnswerStreamError() from None
        else:
            raise AnswerStreamError() from None
    return decoded, closed


def _chunks(text: str) -> tuple[str, ...]:
    if not text:
        return ()
    return tuple(text[index : index + 2048] for index in range(0, len(text), 2048))
