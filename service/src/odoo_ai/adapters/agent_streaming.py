"""Safe incremental extraction of the user-visible answer from structured Codex output."""

from __future__ import annotations

from dataclasses import dataclass, field

_TARGET_KEY = "answer_markdown"
_SIMPLE_ESCAPES = {
    '"': '"',
    "\\": "\\",
    "/": "/",
    "b": "\b",
    "f": "\f",
    "n": "\n",
    "r": "\r",
    "t": "\t",
}


@dataclass(slots=True)
class AnswerMarkdownDeltaExtractor:
    """Emit only the decoded top-level ``answer_markdown`` JSON string.

    Codex streams the complete structured JSON object through agent-message deltas. The browser
    must never receive that raw object because it also contains plan/tool metadata. This tiny
    state machine follows top-level JSON keys and starts decoding only after it has positively
    matched the ``answer_markdown`` key and its string value.
    """

    max_output_bytes: int = 16 * 1024
    _depth: int = 0
    _in_string: bool = False
    _string_escape: bool = False
    _capture_key: bool = False
    _key_invalid: bool = False
    _key_chars: list[str] = field(default_factory=list)
    _expect_key: bool = False
    _target_key_closed: bool = False
    _await_target_value: bool = False
    _in_target_value: bool = False
    _value_escape: bool = False
    _unicode_digits: str | None = None
    _pending_high_surrogate: int | None = None
    _output_bytes: int = 0
    _done: bool = False

    def feed(self, chunk: str) -> str:
        """Consume one raw structured-output delta and return newly visible answer text."""

        if self._done or not chunk:
            return ""
        output: list[str] = []
        for character in chunk:
            if self._done:
                break
            if self._in_target_value:
                self._consume_target_character(character, output)
                continue
            if self._in_string:
                self._consume_other_string_character(character)
                continue
            if self._await_target_value:
                if character.isspace():
                    continue
                if character == '"':
                    self._await_target_value = False
                    self._in_target_value = True
                    continue
                # The output is not shaped like the contract. Stop provisional streaming but let
                # the final structured-output validation decide the turn outcome.
                self._done = True
                continue
            if self._target_key_closed:
                if character.isspace():
                    continue
                self._target_key_closed = False
                if character == ":":
                    self._await_target_value = True
                    continue
                self._done = True
                continue
            if character == '"':
                self._in_string = True
                self._string_escape = False
                self._capture_key = self._depth == 1 and self._expect_key
                self._key_invalid = False
                self._key_chars.clear()
                continue
            if character == "{":
                self._depth += 1
                if self._depth == 1:
                    self._expect_key = True
                continue
            if character == "[":
                self._depth += 1
                continue
            if character in "}]":
                self._depth -= 1
                if self._depth < 0:
                    self._done = True
                continue
            if character == "," and self._depth == 1:
                self._expect_key = True
                continue
            if character == ":" and self._depth == 1:
                self._expect_key = False
        return "".join(output)

    @property
    def completed(self) -> bool:
        return self._done

    def _consume_other_string_character(self, character: str) -> None:
        if self._string_escape:
            self._string_escape = False
            if self._capture_key:
                self._key_invalid = True
            return
        if character == "\\":
            self._string_escape = True
            return
        if character != '"':
            if self._capture_key and not self._key_invalid:
                self._key_chars.append(character)
            return
        self._in_string = False
        if self._capture_key:
            self._expect_key = False
            if not self._key_invalid and "".join(self._key_chars) == _TARGET_KEY:
                self._target_key_closed = True
        self._capture_key = False
        self._key_chars.clear()

    def _consume_target_character(self, character: str, output: list[str]) -> None:
        if self._unicode_digits is not None:
            if character not in "0123456789abcdefABCDEF":
                self._done = True
                return
            self._unicode_digits += character
            if len(self._unicode_digits) == 4:
                codepoint = int(self._unicode_digits, 16)
                self._unicode_digits = None
                self._value_escape = False
                self._emit_codepoint(codepoint, output)
            return
        if self._value_escape:
            if character == "u":
                self._unicode_digits = ""
                return
            decoded = _SIMPLE_ESCAPES.get(character)
            self._value_escape = False
            if decoded is None or self._pending_high_surrogate is not None:
                self._done = True
                return
            self._emit(decoded, output)
            return
        if character == "\\":
            self._value_escape = True
            return
        if character == '"':
            if self._pending_high_surrogate is not None:
                self._done = True
                return
            self._in_target_value = False
            self._done = True
            return
        if self._pending_high_surrogate is not None:
            self._done = True
            return
        self._emit(character, output)

    def _emit_codepoint(self, codepoint: int, output: list[str]) -> None:
        if 0xD800 <= codepoint <= 0xDBFF:
            if self._pending_high_surrogate is not None:
                self._done = True
                return
            self._pending_high_surrogate = codepoint
            return
        if 0xDC00 <= codepoint <= 0xDFFF:
            high = self._pending_high_surrogate
            if high is None:
                self._done = True
                return
            self._pending_high_surrogate = None
            combined = 0x10000 + ((high - 0xD800) << 10) + (codepoint - 0xDC00)
            self._emit(chr(combined), output)
            return
        if self._pending_high_surrogate is not None:
            self._done = True
            return
        self._emit(chr(codepoint), output)

    def _emit(self, value: str, output: list[str]) -> None:
        encoded = value.encode("utf-8")
        if self._output_bytes + len(encoded) > self.max_output_bytes:
            self._done = True
            return
        self._output_bytes += len(encoded)
        output.append(value)
