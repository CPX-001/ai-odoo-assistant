"""Short-lived a1 authority minted only from a consumed durable approval."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import stat
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Final

from pydantic import ValidationError

from odoo_ai.contracts import ActionAuthorityClaims

ACTION_AUTHORITY_SECRET_FILE_ENV: Final = "ODOO_AI_ACTION_AUTHORITY_SECRET_FILE"
ACTION_AUTHORITY_PREFIX: Final = "a1"
ACTION_AUTHORITY_KEY_PURPOSE: Final = b"odoo-ai-assistant/action-authority/v1"
MAX_AUTHORITY_BYTES: Final = 8192
MAX_AUTHORITY_TTL_SECONDS: Final = 120
MAX_CLOCK_SKEW_SECONDS: Final = 5


class ActionAuthorityError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class ActionAuthorityCodec:
    """Canonical HMAC codec isolated from v1, q1, and p1 token families."""

    def __init__(self, root_secret: bytes, *, clock: Callable[[], int] | None = None) -> None:
        if len(root_secret) < 43:
            raise ActionAuthorityError("signing_key_unavailable")
        self._key = hmac.digest(root_secret, ACTION_AUTHORITY_KEY_PURPOSE, hashlib.sha256)
        self._clock = clock or (lambda: int(time.time()))

    @classmethod
    def from_env(
        cls,
        environ: Mapping[str, str] | None = None,
        *,
        clock: Callable[[], int] | None = None,
    ) -> ActionAuthorityCodec:
        source = os.environ if environ is None else environ
        path = source.get(ACTION_AUTHORITY_SECRET_FILE_ENV, "").strip()
        if not path:
            raise ActionAuthorityError("signing_key_unconfigured")
        return cls(_read_secret(Path(path)), clock=clock)

    def encode(self, claims: ActionAuthorityClaims) -> str:
        self._validate_time(claims)
        payload = _canonical(claims)
        encoded = _encode(payload)
        signed = f"{ACTION_AUTHORITY_PREFIX}.{encoded}".encode("ascii")
        signature = hmac.digest(self._key, signed, hashlib.sha256)
        return f"{ACTION_AUTHORITY_PREFIX}.{encoded}.{_encode(signature)}"

    def decode(self, token: str) -> ActionAuthorityClaims:
        if not isinstance(token, str) or not token or len(token) > MAX_AUTHORITY_BYTES:
            raise ActionAuthorityError("malformed_token")
        parts = token.split(".")
        if len(parts) != 3 or parts[0] != ACTION_AUTHORITY_PREFIX:
            raise ActionAuthorityError("unknown_version")
        payload = _decode(parts[1])
        signature = _decode(parts[2])
        signed = f"{parts[0]}.{parts[1]}".encode("ascii")
        if len(signature) != 32 or not hmac.compare_digest(
            signature, hmac.digest(self._key, signed, hashlib.sha256)
        ):
            raise ActionAuthorityError("invalid_signature")
        try:
            claims = ActionAuthorityClaims.model_validate_json(payload)
        except ValidationError:
            raise ActionAuthorityError("invalid_claims") from None
        if not hmac.compare_digest(payload, _canonical(claims)):
            raise ActionAuthorityError("noncanonical_payload")
        self._validate_time(claims)
        return claims

    def _validate_time(self, claims: ActionAuthorityClaims) -> None:
        now = self._clock()
        if type(now) is not int:
            raise ActionAuthorityError("clock_unavailable")
        if (
            claims.issued_at > now + MAX_CLOCK_SKEW_SECONDS
            or not 0 < claims.expires_at - claims.issued_at <= MAX_AUTHORITY_TTL_SECONDS
        ):
            raise ActionAuthorityError("invalid_time")
        if now >= claims.expires_at:
            raise ActionAuthorityError("expired")


def _read_secret(path: Path) -> bytes:
    try:
        metadata = path.stat()
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_size > 4096
            or metadata.st_mode & 0o007
        ):
            raise OSError
        value = path.read_bytes().strip()
    except OSError:
        raise ActionAuthorityError("signing_key_unavailable") from None
    if len(value) < 43 or b"\n" in value or b"\r" in value:
        raise ActionAuthorityError("signing_key_unavailable")
    return value


def _canonical(claims: ActionAuthorityClaims) -> bytes:
    return json.dumps(
        claims.model_dump(mode="json"),
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _decode(value: str) -> bytes:
    try:
        if not value or "=" in value:
            raise ValueError
        return base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)
    except (ValueError, UnicodeError):
        raise ActionAuthorityError("malformed_token") from None
