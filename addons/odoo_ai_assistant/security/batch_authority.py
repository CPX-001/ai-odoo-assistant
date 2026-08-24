"""Odoo-side verifier for one exact Assistant Service b1 batch chunk."""

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

from .action_authority import ACTION_AUTHORITY_SECRET_FILE_ENV
from .delegation import DelegationTokenError

_PREFIX: Final = "b1"
_PURPOSE: Final = b"odoo-ai-assistant/batch-authority/v1"
MAX_BATCH_FIELDS: Final = 64
_MODEL = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]{0,127}$")
_FIELD = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")
_JTI = re.compile(r"^[A-Za-z0-9_-]{22,64}$")
_JOB_FINGERPRINT = re.compile(r"^batch-job:v1:sha256:[0-9a-f]{64}$")
_CHUNK_FINGERPRINT = re.compile(r"^batch-chunk:v1:sha256:[0-9a-f]{64}$")
_SCHEMA_FINGERPRINT = re.compile(r"^[a-z][a-z0-9_-]{0,31}:v[0-9]+:sha256:[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class BatchAuthorityPayload:
    format_version: int
    jti: str
    job_id: UUID
    attempt_id: UUID
    authorization_id: UUID
    job_fingerprint: str
    chunk_fingerprint: str
    instance_id: str
    database: str
    uid: int
    company_id: int
    allowed_company_ids: tuple[int, ...]
    operation: str
    model: str
    schema_id: str | None
    fields: tuple[str, ...]
    failure_mode: str
    policy_revision: str
    row_count: int
    scopes: tuple[str, ...]
    issued_at: int
    expires_at: int

    @classmethod
    def from_mapping(cls, raw: dict[str, object]) -> BatchAuthorityPayload:
        expected = {
            "allowed_company_ids",
            "attempt_id",
            "authorization_id",
            "chunk_fingerprint",
            "company_id",
            "database",
            "expires_at",
            "failure_mode",
            "fields",
            "format_version",
            "instance_id",
            "issued_at",
            "job_fingerprint",
            "job_id",
            "jti",
            "model",
            "operation",
            "policy_revision",
            "row_count",
            "schema_id",
            "scopes",
            "uid",
        }
        if set(raw) != expected:
            raise DelegationTokenError("invalid_batch_authority")
        try:
            value = cls(
                format_version=_integer(raw["format_version"]),
                jti=_text(raw["jti"]),
                job_id=UUID(_text(raw["job_id"])),
                attempt_id=UUID(_text(raw["attempt_id"])),
                authorization_id=UUID(_text(raw["authorization_id"])),
                job_fingerprint=_text(raw["job_fingerprint"]),
                chunk_fingerprint=_text(raw["chunk_fingerprint"]),
                instance_id=_text(raw["instance_id"]),
                database=_text(raw["database"]),
                uid=_integer(raw["uid"]),
                company_id=_integer(raw["company_id"]),
                allowed_company_ids=tuple(_integers(raw["allowed_company_ids"])),
                operation=_text(raw["operation"]),
                model=_text(raw["model"]),
                schema_id=_optional_text(raw["schema_id"]),
                fields=tuple(_texts(raw["fields"])),
                failure_mode=_text(raw["failure_mode"]),
                policy_revision=_text(raw["policy_revision"]),
                row_count=_integer(raw["row_count"]),
                scopes=tuple(_texts(raw["scopes"])),
                issued_at=_integer(raw["issued_at"]),
                expires_at=_integer(raw["expires_at"]),
            )
            value._validate()
            return value
        except (TypeError, ValueError):
            raise DelegationTokenError("invalid_batch_authority") from None

    def _validate(self) -> None:
        write = self.operation in {"create", "patch"}
        if (
            self.format_version != 1
            or not _JTI.fullmatch(self.jti)
            or not _JOB_FINGERPRINT.fullmatch(self.job_fingerprint)
            or not _CHUNK_FINGERPRINT.fullmatch(self.chunk_fingerprint)
            or not 1 <= self.uid
            or not 1 <= self.company_id
            or not 1 <= len(self.database) <= 128
            or self.database != self.database.strip()
            or any(ord(character) < 32 for character in self.database)
            or not 1 <= len(self.instance_id) <= 255
            or self.instance_id != self.instance_id.strip()
            or any(ord(character) < 32 for character in self.instance_id)
            or not _MODEL.fullmatch(self.model)
            or not 1 <= len(self.allowed_company_ids) <= 16
            or self.allowed_company_ids != tuple(sorted(set(self.allowed_company_ids)))
            or self.company_id not in self.allowed_company_ids
            or self.operation not in {"create", "patch", "delete"}
            or self.fields != tuple(sorted(set(self.fields)))
            or len(self.fields) > MAX_BATCH_FIELDS
            or any(not _FIELD.fullmatch(field) for field in self.fields)
            or self.failure_mode not in {"continue_on_error", "atomic_chunk"}
            or not 1 <= self.row_count <= 200
            or self.scopes != ("batch_commit",)
            or not 1 <= len(self.policy_revision) <= 128
            or (
                write
                and (
                    self.schema_id is None
                    or not _SCHEMA_FINGERPRINT.fullmatch(self.schema_id)
                    or not self.fields
                )
            )
            or (self.operation == "delete" and (self.schema_id is not None or self.fields))
            or not 0 < self.expires_at - self.issued_at <= 120
        ):
            raise ValueError


class BatchAuthorityCodec:
    def __init__(
        self,
        secret: bytes,
        *,
        clock: Callable[[], int] | None = None,
    ) -> None:
        if len(secret) < 43:
            raise DelegationTokenError("signing_key_unavailable")
        self._key = hmac.digest(secret, _PURPOSE, hashlib.sha256)
        self._clock = clock or (lambda: int(time.time()))

    @classmethod
    def from_env(
        cls,
        *,
        clock: Callable[[], int] | None = None,
    ) -> BatchAuthorityCodec:
        path = os.environ.get(ACTION_AUTHORITY_SECRET_FILE_ENV, "").strip()
        if not path:
            raise DelegationTokenError("signing_key_unavailable")
        return cls(_read_secret(Path(path)), clock=clock)

    def decode(self, token: str) -> BatchAuthorityPayload:
        if not isinstance(token, str) or not token or len(token) > 8192:
            raise DelegationTokenError("malformed_token")
        parts = token.split(".")
        if len(parts) != 3 or parts[0] != _PREFIX:
            raise DelegationTokenError("unknown_version")
        payload = _decode(parts[1])
        signature = _decode(parts[2])
        signed = f"{parts[0]}.{parts[1]}".encode("ascii")
        if len(signature) != 32 or not hmac.compare_digest(
            signature,
            hmac.digest(self._key, signed, hashlib.sha256),
        ):
            raise DelegationTokenError("invalid_signature")
        try:
            raw = json.loads(payload)
        except (UnicodeError, ValueError):
            raise DelegationTokenError("malformed_token") from None
        if not isinstance(raw, dict) or not all(isinstance(key, str) for key in raw):
            raise DelegationTokenError("invalid_batch_authority")
        claims = BatchAuthorityPayload.from_mapping(raw)
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
        if type(now) is not int or claims.issued_at > now + 5 or now >= claims.expires_at:
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
            value + "=" * (-len(value) % 4),
            altchars=b"-_",
            validate=True,
        )
    except (ValueError, UnicodeError):
        raise DelegationTokenError("malformed_token") from None


def _text(value: object) -> str:
    if not isinstance(value, str):
        raise TypeError
    return value


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    return _text(value)


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
