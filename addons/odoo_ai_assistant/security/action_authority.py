"""Odoo-side verifier for the Assistant Service's isolated a1 authority."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import stat
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Final
from uuid import UUID

from .delegation import DelegationTokenError

ACTION_AUTHORITY_SECRET_FILE_ENV: Final = "ODOO_AI_ACTION_AUTHORITY_SECRET_FILE"
_PREFIX: Final = "a1"
_PURPOSE: Final = b"odoo-ai-assistant/action-authority/v1"
_FIELDS = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")
_MODEL = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]{0,127}$")
_FINGERPRINT = re.compile(r"^action-(?:payload|precondition):v1:sha256:[0-9a-f]{64}$")
_JTI = re.compile(r"^[A-Za-z0-9_-]{22,64}$")


@dataclass(frozen=True, slots=True)
class ActionAuthorityPayload:
    format_version: int
    jti: str
    proposal_id: UUID
    approval_id: UUID
    attempt_id: UUID
    instance_id: str
    database: str
    uid: int
    company_id: int
    allowed_company_ids: tuple[int, ...]
    model: str
    record_id: int
    fields: tuple[str, ...]
    payload_fingerprint: str
    precondition_fingerprint: str
    policy_revision: str
    schema_revision: str
    scopes: tuple[str, ...]
    issued_at: int
    expires_at: int

    @classmethod
    def from_mapping(cls, raw: dict[str, object]) -> ActionAuthorityPayload:
        expected = {
            "allowed_company_ids",
            "approval_id",
            "attempt_id",
            "company_id",
            "database",
            "expires_at",
            "fields",
            "format_version",
            "issued_at",
            "instance_id",
            "jti",
            "model",
            "payload_fingerprint",
            "policy_revision",
            "precondition_fingerprint",
            "proposal_id",
            "record_id",
            "schema_revision",
            "scopes",
            "uid",
        }
        if set(raw) != expected:
            raise DelegationTokenError("invalid_action_authority")
        try:
            value = cls(
                format_version=_integer(raw["format_version"]),
                jti=_text(raw["jti"]),
                proposal_id=UUID(_text(raw["proposal_id"])),
                approval_id=UUID(_text(raw["approval_id"])),
                attempt_id=UUID(_text(raw["attempt_id"])),
                instance_id=_text(raw["instance_id"]),
                database=_text(raw["database"]),
                uid=_integer(raw["uid"]),
                company_id=_integer(raw["company_id"]),
                allowed_company_ids=tuple(_integers(raw["allowed_company_ids"])),
                model=_text(raw["model"]),
                record_id=_integer(raw["record_id"]),
                fields=tuple(_texts(raw["fields"])),
                payload_fingerprint=_text(raw["payload_fingerprint"]),
                precondition_fingerprint=_text(raw["precondition_fingerprint"]),
                policy_revision=_text(raw["policy_revision"]),
                schema_revision=_text(raw["schema_revision"]),
                scopes=tuple(_texts(raw["scopes"])),
                issued_at=_integer(raw["issued_at"]),
                expires_at=_integer(raw["expires_at"]),
            )
            value._validate()
            return value
        except (TypeError, ValueError):
            raise DelegationTokenError("invalid_action_authority") from None

    def _validate(self) -> None:
        if (
            self.format_version != 1
            or not _JTI.fullmatch(self.jti)
            or not 1 <= self.uid
            or not 1 <= self.company_id
            or not 1 <= self.record_id
            or not 1 <= len(self.database) <= 128
            or self.database != self.database.strip()
            or not 1 <= len(self.instance_id) <= 255
            or self.instance_id != self.instance_id.strip()
            or not _MODEL.fullmatch(self.model)
            or not 1 <= len(self.allowed_company_ids) <= 16
            or self.allowed_company_ids != tuple(sorted(set(self.allowed_company_ids)))
            or self.company_id not in self.allowed_company_ids
            or not 1 <= len(self.fields) <= 4
            or self.fields != tuple(sorted(set(self.fields)))
            or any(not _FIELDS.fullmatch(field) for field in self.fields)
            or self.scopes not in {("action_commit",), ("action_verify",)}
            or not _FINGERPRINT.fullmatch(self.payload_fingerprint)
            or not _FINGERPRINT.fullmatch(self.precondition_fingerprint)
            or not 1 <= len(self.policy_revision) <= 128
            or not 1 <= len(self.schema_revision) <= 128
            or not 0 < self.expires_at - self.issued_at <= 120
        ):
            raise ValueError


class ActionAuthorityCodec:
    def __init__(
        self, secret: bytes, *, clock: Callable[[], int] | None = None
    ) -> None:
        if len(secret) < 43:
            raise DelegationTokenError("signing_key_unavailable")
        self._key = hmac.digest(secret, _PURPOSE, hashlib.sha256)
        self._clock = clock or (lambda: int(time.time()))

    @classmethod
    def from_env(
        cls, *, clock: Callable[[], int] | None = None
    ) -> ActionAuthorityCodec:
        path = os.environ.get(ACTION_AUTHORITY_SECRET_FILE_ENV, "").strip()
        if not path:
            raise DelegationTokenError("signing_key_unavailable")
        return cls(_read_secret(Path(path)), clock=clock)

    def decode(self, token: str) -> ActionAuthorityPayload:
        if not isinstance(token, str) or not token or len(token) > 8192:
            raise DelegationTokenError("malformed_token")
        parts = token.split(".")
        if len(parts) != 3 or parts[0] != _PREFIX:
            raise DelegationTokenError("unknown_version")
        payload = _decode(parts[1])
        signature = _decode(parts[2])
        signed = f"{parts[0]}.{parts[1]}".encode("ascii")
        if len(signature) != 32 or not hmac.compare_digest(
            signature, hmac.digest(self._key, signed, hashlib.sha256)
        ):
            raise DelegationTokenError("invalid_signature")
        try:
            raw = json.loads(payload)
        except (UnicodeError, ValueError):
            raise DelegationTokenError("malformed_token") from None
        if not isinstance(raw, dict) or not all(isinstance(key, str) for key in raw):
            raise DelegationTokenError("invalid_action_authority")
        claims = ActionAuthorityPayload.from_mapping(raw)
        canonical = json.dumps(
            raw,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
        if not hmac.compare_digest(payload, canonical):
            raise DelegationTokenError("noncanonical_payload")
        now = self._clock()
        if (
            type(now) is not int
            or claims.issued_at > now + 5
            or now >= claims.expires_at
        ):
            raise DelegationTokenError("expired")
        return claims


def _read_secret(path: Path) -> bytes:
    try:
        metadata = path.stat()
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_size > 4096
            or metadata.st_mode & 0o007
        ):
            raise OSError
        secret = path.read_bytes().strip()
    except OSError:
        raise DelegationTokenError("signing_key_unavailable") from None
    if len(secret) < 43 or b"\n" in secret or b"\r" in secret:
        raise DelegationTokenError("signing_key_unavailable")
    return secret


def _decode(value: str) -> bytes:
    try:
        if not value or "=" in value:
            raise ValueError
        return base64.b64decode(
            value + "=" * (-len(value) % 4), altchars=b"-_", validate=True
        )
    except (ValueError, UnicodeError):
        raise DelegationTokenError("malformed_token") from None


def _text(value: object) -> str:
    if not isinstance(value, str):
        raise TypeError
    return value


def _integer(value: object) -> int:
    if type(value) is not int:
        raise TypeError
    return value


def _texts(value: object) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise TypeError
    return value


def _integers(value: object) -> list[int]:
    if not isinstance(value, list) or any(type(item) is not int for item in value):
        raise TypeError
    return value
