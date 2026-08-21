"""Short-lived HMAC delegation signed and verified only inside Odoo.

The Assistant Service transports these tokens but must not receive the root
signing secret. This is deliberately separate from the M1 machine-auth secret,
which is readable by both peers and therefore cannot establish user authority.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import re
import stat
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal, cast
from uuid import UUID

FORMAT_VERSION: Final = 1
TOKEN_PREFIX: Final = "v1"
KEY_PURPOSE: Final = b"odoo-ai-assistant/delegation/v1"
MAX_ALLOWED_COMPANY_IDS: Final = 16
MAX_DELEGATED_RECORD_IDS: Final = 8
MAX_DELEGATION_SCOPES: Final = 2
MAX_DELEGATION_TTL_SECONDS: Final = 120
MAX_DELEGATED_FIELDS: Final = 64
MAX_TOKEN_BYTES: Final = 4096
MAX_CLOCK_SKEW_SECONDS: Final = 5
MIN_SECRET_BYTES: Final = 43
ALLOWED_SCOPES: Final = frozenset({"fields_get", "read_records"})

DelegationScope = Literal["fields_get", "read_records"]
JsonValue = str | int | list["JsonValue"] | dict[str, "JsonValue"] | None

_JTI_PATTERN = re.compile(r"^[A-Za-z0-9_-]{22,64}$")
_MODEL_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]{0,127}$")


class DelegationTokenError(ValueError):
    """Sanitized token failure that never includes credential material."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class DelegationPayload:
    """Closed claim set used by the addon signer and future addon verifier."""

    format_version: int
    jti: str
    turn_id: UUID
    database: str
    uid: int
    company_id: int
    allowed_company_ids: tuple[int, ...]
    lang: str | None
    model: str
    record_ids: tuple[int, ...]
    scopes: tuple[DelegationScope, ...]
    issued_at: int
    expires_at: int
    max_records: int
    max_fields: int

    def __post_init__(self) -> None:
        try:
            self._validate()
        except (TypeError, ValueError) as error:
            raise DelegationTokenError("invalid_claims") from error

    def _validate(self) -> None:
        if type(self.format_version) is not int or self.format_version != FORMAT_VERSION:
            raise ValueError
        if not _JTI_PATTERN.fullmatch(self.jti):
            raise ValueError
        if not isinstance(self.turn_id, UUID):
            raise TypeError
        _validate_text(self.database, maximum=128)
        _validate_positive_int(self.uid)
        _validate_positive_int(self.company_id)
        _validate_positive_ids(
            self.allowed_company_ids, maximum=MAX_ALLOWED_COMPANY_IDS
        )
        if self.company_id not in self.allowed_company_ids:
            raise ValueError
        if self.lang is not None:
            _validate_text(self.lang, minimum=2, maximum=35)
        if not _MODEL_PATTERN.fullmatch(self.model):
            raise ValueError
        _validate_positive_ids(self.record_ids, maximum=MAX_DELEGATED_RECORD_IDS)
        if not 1 <= len(self.scopes) <= MAX_DELEGATION_SCOPES:
            raise ValueError
        if len(self.scopes) != len(set(self.scopes)):
            raise ValueError
        if any(scope not in ALLOWED_SCOPES for scope in self.scopes):
            raise ValueError
        if type(self.issued_at) is not int or self.issued_at < 0:
            raise ValueError
        if type(self.expires_at) is not int or self.expires_at < 0:
            raise ValueError
        if not 0 < self.expires_at - self.issued_at <= MAX_DELEGATION_TTL_SECONDS:
            raise ValueError
        _validate_positive_int(self.max_records)
        if self.max_records > len(self.record_ids):
            raise ValueError
        _validate_positive_int(self.max_fields)
        if self.max_fields > MAX_DELEGATED_FIELDS:
            raise ValueError

    def to_mapping(self) -> dict[str, JsonValue]:
        """Return the exact canonical claim shape without extensible values."""

        return {
            "allowed_company_ids": list(self.allowed_company_ids),
            "company_id": self.company_id,
            "database": self.database,
            "expires_at": self.expires_at,
            "format_version": self.format_version,
            "issued_at": self.issued_at,
            "jti": self.jti,
            "lang": self.lang,
            "max_fields": self.max_fields,
            "max_records": self.max_records,
            "model": self.model,
            "record_ids": list(self.record_ids),
            "scopes": list(self.scopes),
            "turn_id": str(self.turn_id),
            "uid": self.uid,
        }

    @classmethod
    def from_mapping(cls, raw: Mapping[str, object]) -> DelegationPayload:
        expected = {
            "allowed_company_ids",
            "company_id",
            "database",
            "expires_at",
            "format_version",
            "issued_at",
            "jti",
            "lang",
            "max_fields",
            "max_records",
            "model",
            "record_ids",
            "scopes",
            "turn_id",
            "uid",
        }
        if set(raw) != expected:
            raise DelegationTokenError("invalid_claims")
        try:
            version = _require_int(raw["format_version"])
            if version != FORMAT_VERSION:
                raise DelegationTokenError("unknown_version")
            scopes = tuple(
                cast(DelegationScope, scope)
                for scope in _require_string_list(raw["scopes"])
            )
            return cls(
                format_version=version,
                jti=_require_string(raw["jti"]),
                turn_id=UUID(_require_string(raw["turn_id"])),
                database=_require_string(raw["database"]),
                uid=_require_int(raw["uid"]),
                company_id=_require_int(raw["company_id"]),
                allowed_company_ids=tuple(
                    _require_int_list(raw["allowed_company_ids"])
                ),
                lang=_require_optional_string(raw["lang"]),
                model=_require_string(raw["model"]),
                record_ids=tuple(_require_int_list(raw["record_ids"])),
                scopes=scopes,
                issued_at=_require_int(raw["issued_at"]),
                expires_at=_require_int(raw["expires_at"]),
                max_records=_require_int(raw["max_records"]),
                max_fields=_require_int(raw["max_fields"]),
            )
        except DelegationTokenError:
            raise
        except (TypeError, ValueError) as error:
            raise DelegationTokenError("invalid_claims") from error


class DelegationCodec:
    """Canonical HMAC-SHA256 codec with an injectable wall clock."""

    __slots__ = ("_clock", "_signing_key")

    def __init__(
        self,
        root_secret: bytes,
        *,
        clock: Callable[[], int] | None = None,
    ) -> None:
        if len(root_secret) < MIN_SECRET_BYTES:
            raise DelegationTokenError("signing_key_unavailable")
        self._signing_key = hmac.digest(root_secret, KEY_PURPOSE, hashlib.sha256)
        self._clock = clock or _unix_time

    @classmethod
    def from_secret_file(
        cls,
        path: str | Path,
        *,
        clock: Callable[[], int] | None = None,
    ) -> DelegationCodec:
        return cls(_read_secret_file(Path(path)), clock=clock)

    def encode(self, payload: DelegationPayload) -> str:
        self._validate_time(payload)
        encoded_payload = _base64url_encode(_canonical_payload(payload))
        signed = f"{TOKEN_PREFIX}.{encoded_payload}".encode("ascii")
        signature = hmac.digest(self._signing_key, signed, hashlib.sha256)
        return f"{TOKEN_PREFIX}.{encoded_payload}.{_base64url_encode(signature)}"

    def decode(self, token: str) -> DelegationPayload:
        try:
            encoded = token.encode("ascii")
        except (AttributeError, UnicodeEncodeError) as error:
            raise DelegationTokenError("malformed_token") from error
        if not encoded or len(encoded) > MAX_TOKEN_BYTES:
            raise DelegationTokenError("malformed_token")
        parts = token.split(".")
        if len(parts) != 3:
            raise DelegationTokenError("malformed_token")
        prefix, encoded_payload, encoded_signature = parts
        if prefix != TOKEN_PREFIX:
            raise DelegationTokenError("unknown_version")
        signed = f"{prefix}.{encoded_payload}".encode("ascii")
        signature = _base64url_decode(encoded_signature)
        if len(signature) != hashlib.sha256().digest_size:
            raise DelegationTokenError("malformed_token")
        expected = hmac.digest(self._signing_key, signed, hashlib.sha256)
        if not hmac.compare_digest(signature, expected):
            raise DelegationTokenError("invalid_signature")
        payload_bytes = _base64url_decode(encoded_payload)
        try:
            loaded: object = json.loads(payload_bytes)
        except (UnicodeError, json.JSONDecodeError) as error:
            raise DelegationTokenError("malformed_token") from error
        if not isinstance(loaded, dict) or not all(
            isinstance(key, str) for key in loaded
        ):
            raise DelegationTokenError("invalid_claims")
        payload = DelegationPayload.from_mapping(cast(dict[str, object], loaded))
        if not hmac.compare_digest(_canonical_payload(payload), payload_bytes):
            raise DelegationTokenError("noncanonical_payload")
        self._validate_time(payload)
        return payload

    def _validate_time(self, payload: DelegationPayload) -> None:
        now = self._clock()
        if type(now) is not int:
            raise DelegationTokenError("clock_unavailable")
        if payload.issued_at > now + MAX_CLOCK_SKEW_SECONDS:
            raise DelegationTokenError("not_yet_valid")
        if now >= payload.expires_at:
            raise DelegationTokenError("expired")


def _read_secret_file(path: Path) -> bytes:
    try:
        metadata = path.stat()
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_size > 4096
            or metadata.st_mode & 0o007
        ):
            raise OSError
        secret = path.read_bytes().strip()
    except OSError as error:
        raise DelegationTokenError("signing_key_unavailable") from error
    if len(secret) < MIN_SECRET_BYTES or b"\n" in secret or b"\r" in secret:
        raise DelegationTokenError("signing_key_unavailable")
    return secret


def _canonical_payload(payload: DelegationPayload) -> bytes:
    return json.dumps(
        payload.to_mapping(),
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")


def _base64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _base64url_decode(value: str) -> bytes:
    if not value or "=" in value:
        raise DelegationTokenError("malformed_token")
    try:
        raw = value.encode("ascii")
        padding = b"=" * (-len(raw) % 4)
        decoded = base64.b64decode(raw + padding, altchars=b"-_", validate=True)
    except (UnicodeEncodeError, binascii.Error, ValueError) as error:
        raise DelegationTokenError("malformed_token") from error
    if not hmac.compare_digest(_base64url_encode(decoded), value):
        raise DelegationTokenError("malformed_token")
    return decoded


def _unix_time() -> int:
    return int(time.time())


def _validate_text(value: str, *, minimum: int = 1, maximum: int) -> None:
    if not isinstance(value, str) or not minimum <= len(value) <= maximum:
        raise ValueError
    if value != value.strip() or any(ord(character) < 32 for character in value):
        raise ValueError


def _validate_positive_int(value: int) -> None:
    if type(value) is not int or value <= 0:
        raise ValueError


def _validate_positive_ids(values: tuple[int, ...], *, maximum: int) -> None:
    if not isinstance(values, tuple) or not 1 <= len(values) <= maximum:
        raise ValueError
    if len(values) != len(set(values)):
        raise ValueError
    for value in values:
        _validate_positive_int(value)


def _require_string(value: object) -> str:
    if not isinstance(value, str):
        raise TypeError
    return value


def _require_optional_string(value: object) -> str | None:
    if value is None:
        return None
    return _require_string(value)


def _require_int(value: object) -> int:
    if type(value) is not int:
        raise TypeError
    return value


def _require_int_list(value: object) -> list[int]:
    if not isinstance(value, list):
        raise TypeError
    return [_require_int(item) for item in value]


def _require_string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        raise TypeError
    return [_require_string(item) for item in value]
