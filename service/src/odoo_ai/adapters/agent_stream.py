"""Provider-neutral per-turn answer streaming helpers.

The reasoning adapter may emit only user-visible answer text through this boundary. Tool payloads,
reasoning, plans, authority handles, and provider-specific event data never cross it.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar

from odoo_ai.adapters.codex_engine import CodexEngineError

MAX_STREAM_BUFFER_CHARS = 64 * 1024
MAX_STREAM_ANSWER_CHARS = 16_384

AnswerDeltaSink = Callable[[str], None]
_ACTIVE_ANSWER_SINK: ContextVar[AnswerDeltaSink | None] = ContextVar(
    "odoo_ai_active_answer_sink",
    default=None,
)


@contextmanager
def bind_answer_delta_sink(sink: AnswerDeltaSink | None) -> Iterator[None]:
    """Bind one sink to the current async task/context only."""

    token = _ACTIVE_ANSWER_SINK.set(sink)
    try:
        yield
    finally:
        _ACTIVE_ANSWER_SINK.reset(token)


def emit_answer_delta(text: str) -> None:
    """Emit bounded visible text when a streaming transport is active."""

    if not text:
        return
    sink = _ACTIVE_ANSWER_SINK.get()
    if sink is not None:
        sink(text)


class StructuredAnswerMarkdownExtractor:
    """Extract only ``answer_markdown`` from incremental structured JSON output.

    Codex receives a structured output schema, so its agent-message deltas contain pieces of the
    JSON object rather than a plain user-visible message. This extractor intentionally ignores every
    other property and incrementally decodes only the JSON string value of ``answer_markdown``.
    """

    _MARKER = '"answer_markdown"'

    def __init__(self) -> None:
        self._buffer = ""
        self._value_start: int | None = None
        self._decoded = ""
        self._finished = False

    def feed(self, fragment: str) -> str:
        if self._finished or not fragment:
            return ""
        if not isinstance(fragment, str):
            raise CodexEngineError("codex_stream_delta_invalid")
        self._buffer += fragment
        if len(self._buffer) > MAX_STREAM_BUFFER_CHARS:
            raise CodexEngineError("codex_stream_buffer_exceeded")
        if self._value_start is None:
            marker_at = self._buffer.find(self._MARKER)
            if marker_at < 0:
                return ""
            cursor = marker_at + len(self._MARKER)
            while cursor < len(self._buffer) and self._buffer[cursor].isspace():
                cursor += 1
            if cursor >= len(self._buffer) or self._buffer[cursor] != ":":
                return ""
            cursor += 1
            while cursor < len(self._buffer) and self._buffer[cursor].isspace():
                cursor += 1
            if cursor >= len(self._buffer):
                return ""
            if self._buffer[cursor] != '"':
                raise CodexEngineError("codex_stream_answer_invalid")
            self._value_start = cursor + 1

        raw = self._buffer[self._value_start :]
        complete_raw, closed = _complete_json_string_prefix(raw)
        try:
            decoded = json.loads(f'"{complete_raw}"')
        except (UnicodeError, ValueError):
            raise CodexEngineError("codex_stream_answer_invalid") from None
        if not isinstance(decoded, str) or not decoded.startswith(self._decoded):
            raise CodexEngineError("codex_stream_answer_invalid")
        if len(decoded) > MAX_STREAM_ANSWER_CHARS:
            raise CodexEngineError("codex_answer_too_large")
        delta = decoded[len(self._decoded) :]
        self._decoded = decoded
        if closed:
            self._finished = True
        return delta


def _complete_json_string_prefix(raw: str) -> tuple[str, bool]:
    """Return the largest complete JSON-string content prefix and whether its quote closed."""

    index = 0
    while index < len(raw):
        character = raw[index]
        if character == '"':
            return raw[:index], True
        if character != "\\":
            if ord(character) < 0x20:
                raise CodexEngineError("codex_stream_answer_invalid")
            index += 1
            continue
        escape_start = index
        index += 1
        if index >= len(raw):
            return raw[:escape_start], False
        escape = raw[index]
        if escape == "u":
            if index + 4 >= len(raw):
                return raw[:escape_start], False
            digits = raw[index + 1 : index + 5]
            if len(digits) != 4 or any(char not in "0123456789abcdefABCDEF" for char in digits):
                raise CodexEngineError("codex_stream_answer_invalid")
            index += 5
            continue
        if escape not in {'"', "\\", "/", "b", "f", "n", "r", "t"}:
            raise CodexEngineError("codex_stream_answer_invalid")
        index += 1
    return raw, False
