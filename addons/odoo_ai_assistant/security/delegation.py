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
QUERY_FORMAT_VERSION: Final = 1
QUERY_TOKEN_PREFIX: Final = "q1"
QUERY_KEY_PURPOSE: Final = b"odoo-ai-assistant/query-delegation/v1"
ACTION_PREVIEW_FORMAT_VERSION: Final = 1
ACTION_PREVIEW_TOKEN_PREFIX: Final = "p1"
ACTION_PREVIEW_KEY_PURPOSE: Final = b"odoo-ai-assistant/action-preview-delegation/v1"
AGENT_FORMAT_VERSION: Final = 1
AGENT_TOKEN_PREFIX: Final = "ag1"
AGENT_KEY_PURPOSE: Final = b"odoo-ai-assistant/agent-delegation/v1"
MAX_ALLOWED_COMPANY_IDS: Final = 16
MAX_DELEGATED_RECORD_IDS: Final = 8
MAX_DELEGATION_SCOPES: Final = 2
MAX_DELEGATION_TTL_SECONDS: Final = 120
MAX_AGENT_TTL_SECONDS: Final = 300
MAX_DELEGATED_FIELDS: Final = 64
MAX_TOKEN_BYTES: Final = 4096
MAX_QUERY_TOKEN_BYTES: Final = 8192
MAX_CLOCK_SKEW_SECONDS: Final = 5
MIN_SECRET_BYTES: Final = 43
ALLOWED_SCOPES: Final = frozenset({"fields_get", "navigation", "read_records"})
ALLOWED_QUERY_SCOPES: Final = frozenset(
    {"aggregate_records", "query_records", "query_schema"}
)
ALLOWED_ACTION_PREVIEW_SCOPES: Final = frozenset(
    {"action_preview", "action_write_schema"}
)
ALLOWED_AGENT_SCOPES: Final = frozenset(
    {
        "aggregate_records",
        "query_records",
        "query_schema",
        "action_preview",
        "action_write_schema",
        "model_search",
    }
)
MAX_QUERY_FIELDS: Final = 64
MAX_QUERY_RECORDS: Final = 50
MAX_QUERY_RESULT_FIELDS: Final = 16
MAX_QUERY_CONDITIONS: Final = 8
MAX_QUERY_GROUPS: Final = 50
MAX_QUERY_AGGREGATES: Final = 8

DelegationScope = Literal["fields_get", "navigation", "read_records"]
QueryDelegationScope = Literal["aggregate_records", "query_records", "query_schema"]
ActionPreviewDelegationScope = Literal["action_preview", "action_write_schema"]
AgentDelegationScope = Literal[
    "aggregate_records",
    "query_records",
    "query_schema",
    "action_preview",
    "action_write_schema",
    "model_search",
]
JsonValue = str | int | list["JsonValue"] | dict[str, "JsonValue"] | None

_JTI_PATTERN = re.compile(r"^[A-Za-z0-9_-]{22,64}$")
_MODEL_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]{0,127}$")
_FIELD_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")


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
    model: str | None
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
        if (
            type(self.format_version) is not int
            or self.format_version != FORMAT_VERSION
        ):
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
        if self.model is not None and not _MODEL_PATTERN.fullmatch(self.model):
            raise ValueError
        if self.record_ids:
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
        if type(self.max_records) is not int or self.max_records < 0:
            raise ValueError
        if self.max_records > len(self.record_ids):
            raise ValueError
        if "read_records" in self.scopes and (
            self.model is None or not self.record_ids or self.max_records < 1
        ):
            raise ValueError
        if "fields_get" in self.scopes and self.model is None:
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
                model=_require_optional_string(raw["model"]),
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


@dataclass(frozen=True, slots=True)
class QueryDelegationPayload:
    """Separate q1 authority for one model's bounded QUERY primitives."""

    format_version: int
    jti: str
    turn_id: UUID
    database: str
    uid: int
    company_id: int
    allowed_company_ids: tuple[int, ...]
    lang: str | None
    model: str
    allowed_fields: tuple[str, ...]
    scopes: tuple[QueryDelegationScope, ...]
    issued_at: int
    expires_at: int
    max_records: int
    max_fields: int
    max_conditions: int
    max_groups: int
    max_aggregates: int
    policy_revision: str

    def __post_init__(self) -> None:
        try:
            self._validate()
        except (TypeError, ValueError) as error:
            raise DelegationTokenError("invalid_query_claims") from error

    def _validate(self) -> None:
        if (
            type(self.format_version) is not int
            or self.format_version != QUERY_FORMAT_VERSION
        ):
            raise ValueError
        if not _JTI_PATTERN.fullmatch(self.jti) or not isinstance(self.turn_id, UUID):
            raise ValueError
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
        if (
            not isinstance(self.allowed_fields, tuple)
            or not 1 <= len(self.allowed_fields) <= MAX_QUERY_FIELDS
            or len(self.allowed_fields) != len(set(self.allowed_fields))
            or self.allowed_fields
            != tuple(sorted(self.allowed_fields, key=lambda item: (item != "id", item)))
            or any(not _FIELD_PATTERN.fullmatch(item) for item in self.allowed_fields)
        ):
            raise ValueError
        if not 1 <= len(self.scopes) <= len(ALLOWED_QUERY_SCOPES):
            raise ValueError
        if len(self.scopes) != len(set(self.scopes)) or any(
            scope not in ALLOWED_QUERY_SCOPES for scope in self.scopes
        ):
            raise ValueError
        if type(self.issued_at) is not int or self.issued_at < 0:
            raise ValueError
        if type(self.expires_at) is not int or self.expires_at < 0:
            raise ValueError
        if not 0 < self.expires_at - self.issued_at <= MAX_DELEGATION_TTL_SECONDS:
            raise ValueError
        _validate_bounded_int(self.max_records, minimum=1, maximum=MAX_QUERY_RECORDS)
        _validate_bounded_int(
            self.max_fields, minimum=1, maximum=MAX_QUERY_RESULT_FIELDS
        )
        if self.max_fields > len(self.allowed_fields):
            raise ValueError
        _validate_bounded_int(
            self.max_conditions, minimum=0, maximum=MAX_QUERY_CONDITIONS
        )
        _validate_bounded_int(self.max_groups, minimum=1, maximum=MAX_QUERY_GROUPS)
        _validate_bounded_int(
            self.max_aggregates, minimum=1, maximum=MAX_QUERY_AGGREGATES
        )
        _validate_text(self.policy_revision, maximum=128)

    def to_mapping(self) -> dict[str, JsonValue]:
        return {
            "allowed_company_ids": list(self.allowed_company_ids),
            "allowed_fields": list(self.allowed_fields),
            "company_id": self.company_id,
            "database": self.database,
            "expires_at": self.expires_at,
            "format_version": self.format_version,
            "issued_at": self.issued_at,
            "jti": self.jti,
            "lang": self.lang,
            "max_aggregates": self.max_aggregates,
            "max_conditions": self.max_conditions,
            "max_fields": self.max_fields,
            "max_groups": self.max_groups,
            "max_records": self.max_records,
            "model": self.model,
            "policy_revision": self.policy_revision,
            "scopes": list(self.scopes),
            "turn_id": str(self.turn_id),
            "uid": self.uid,
        }

    @classmethod
    def from_mapping(cls, raw: Mapping[str, object]) -> QueryDelegationPayload:
        expected = {
            "allowed_company_ids",
            "allowed_fields",
            "company_id",
            "database",
            "expires_at",
            "format_version",
            "issued_at",
            "jti",
            "lang",
            "max_aggregates",
            "max_conditions",
            "max_fields",
            "max_groups",
            "max_records",
            "model",
            "policy_revision",
            "scopes",
            "turn_id",
            "uid",
        }
        if set(raw) != expected:
            raise DelegationTokenError("invalid_query_claims")
        try:
            version = _require_int(raw["format_version"])
            if version != QUERY_FORMAT_VERSION:
                raise DelegationTokenError("unknown_version")
            scopes = tuple(
                cast(QueryDelegationScope, scope)
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
                allowed_fields=tuple(_require_string_list(raw["allowed_fields"])),
                scopes=scopes,
                issued_at=_require_int(raw["issued_at"]),
                expires_at=_require_int(raw["expires_at"]),
                max_records=_require_int(raw["max_records"]),
                max_fields=_require_int(raw["max_fields"]),
                max_conditions=_require_int(raw["max_conditions"]),
                max_groups=_require_int(raw["max_groups"]),
                max_aggregates=_require_int(raw["max_aggregates"]),
                policy_revision=_require_string(raw["policy_revision"]),
            )
        except DelegationTokenError:
            raise
        except (TypeError, ValueError) as error:
            raise DelegationTokenError("invalid_query_claims") from error


@dataclass(frozen=True, slots=True)
class ActionPreviewDelegationPayload:
    """Separate p1 authority for write schema and a single effect-free preview."""

    format_version: int
    jti: str
    turn_id: UUID
    database: str
    uid: int
    company_id: int
    allowed_company_ids: tuple[int, ...]
    lang: str | None
    model: str
    record_id: int
    allowed_fields: tuple[str, ...]
    scopes: tuple[ActionPreviewDelegationScope, ...]
    issued_at: int
    expires_at: int
    max_fields: int
    policy_revision: str

    def __post_init__(self) -> None:
        try:
            self._validate()
        except (TypeError, ValueError) as error:
            raise DelegationTokenError("invalid_action_preview_claims") from error

    def _validate(self) -> None:
        if self.format_version != ACTION_PREVIEW_FORMAT_VERSION:
            raise ValueError
        if not _JTI_PATTERN.fullmatch(self.jti) or not isinstance(self.turn_id, UUID):
            raise ValueError
        _validate_text(self.database, maximum=128)
        _validate_positive_int(self.uid)
        _validate_positive_int(self.company_id)
        _validate_positive_ids(
            self.allowed_company_ids, maximum=MAX_ALLOWED_COMPANY_IDS
        )
        if (
            self.company_id not in self.allowed_company_ids
            or self.allowed_company_ids != tuple(sorted(self.allowed_company_ids))
        ):
            raise ValueError
        if self.lang is not None:
            _validate_text(self.lang, minimum=2, maximum=35)
        if not _MODEL_PATTERN.fullmatch(self.model):
            raise ValueError
        _validate_positive_int(self.record_id)
        if (
            not isinstance(self.allowed_fields, tuple)
            or not 1 <= len(self.allowed_fields) <= MAX_DELEGATED_FIELDS
            or len(self.allowed_fields) != len(set(self.allowed_fields))
            or self.allowed_fields != tuple(sorted(self.allowed_fields))
            or any(not _FIELD_PATTERN.fullmatch(item) for item in self.allowed_fields)
        ):
            raise ValueError
        if not 1 <= len(self.scopes) <= len(ALLOWED_ACTION_PREVIEW_SCOPES):
            raise ValueError
        if len(self.scopes) != len(set(self.scopes)) or any(
            scope not in ALLOWED_ACTION_PREVIEW_SCOPES for scope in self.scopes
        ):
            raise ValueError
        if type(self.issued_at) is not int or self.issued_at < 0:
            raise ValueError
        if type(self.expires_at) is not int or self.expires_at < 0:
            raise ValueError
        if not 0 < self.expires_at - self.issued_at <= MAX_DELEGATION_TTL_SECONDS:
            raise ValueError
        _validate_bounded_int(self.max_fields, minimum=1, maximum=MAX_DELEGATED_FIELDS)
        if self.max_fields > len(self.allowed_fields):
            raise ValueError
        _validate_text(self.policy_revision, maximum=128)

    def to_mapping(self) -> dict[str, JsonValue]:
        return {
            "allowed_company_ids": list(self.allowed_company_ids),
            "allowed_fields": list(self.allowed_fields),
            "company_id": self.company_id,
            "database": self.database,
            "expires_at": self.expires_at,
            "format_version": self.format_version,
            "issued_at": self.issued_at,
            "jti": self.jti,
            "lang": self.lang,
            "max_fields": self.max_fields,
            "model": self.model,
            "policy_revision": self.policy_revision,
            "record_id": self.record_id,
            "scopes": list(self.scopes),
            "turn_id": str(self.turn_id),
            "uid": self.uid,
        }

    @classmethod
    def from_mapping(cls, raw: Mapping[str, object]) -> ActionPreviewDelegationPayload:
        expected = {
            "allowed_company_ids",
            "allowed_fields",
            "company_id",
            "database",
            "expires_at",
            "format_version",
            "issued_at",
            "jti",
            "lang",
            "max_fields",
            "model",
            "policy_revision",
            "record_id",
            "scopes",
            "turn_id",
            "uid",
        }
        if set(raw) != expected:
            raise DelegationTokenError("invalid_action_preview_claims")
        try:
            version = _require_int(raw["format_version"])
            if version != ACTION_PREVIEW_FORMAT_VERSION:
                raise DelegationTokenError("unknown_version")
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
                record_id=_require_int(raw["record_id"]),
                allowed_fields=tuple(_require_string_list(raw["allowed_fields"])),
                scopes=tuple(
                    cast(ActionPreviewDelegationScope, scope)
                    for scope in _require_string_list(raw["scopes"])
                ),
                issued_at=_require_int(raw["issued_at"]),
                expires_at=_require_int(raw["expires_at"]),
                max_fields=_require_int(raw["max_fields"]),
                policy_revision=_require_string(raw["policy_revision"]),
            )
        except DelegationTokenError:
            raise
        except (TypeError, ValueError) as error:
            raise DelegationTokenError("invalid_action_preview_claims") from error


@dataclass(frozen=True, slots=True)
class AgentDelegationPayload:
    """One multi-model, preview-only authority for a unified agent turn."""

    format_version: int
    jti: str
    turn_id: UUID
    database: str
    uid: int
    company_id: int
    allowed_company_ids: tuple[int, ...]
    lang: str | None
    allowed_models: tuple[str, ...]
    scopes: tuple[AgentDelegationScope, ...]
    issued_at: int
    expires_at: int
    max_records: int
    max_fields: int
    max_conditions: int
    max_groups: int
    max_aggregates: int
    max_write_steps: int
    policy_revision: str
    allow_runtime_models: bool = False

    def __post_init__(self) -> None:
        try:
            self._validate()
        except (TypeError, ValueError) as error:
            raise DelegationTokenError("invalid_agent_claims") from error

    def _validate(self) -> None:
        if self.format_version != AGENT_FORMAT_VERSION:
            raise ValueError
        if not _JTI_PATTERN.fullmatch(self.jti) or not isinstance(self.turn_id, UUID):
            raise ValueError
        _validate_text(self.database, maximum=128)
        _validate_positive_int(self.uid)
        _validate_positive_int(self.company_id)
        _validate_positive_ids(self.allowed_company_ids, maximum=MAX_ALLOWED_COMPANY_IDS)
        if (
            self.company_id not in self.allowed_company_ids
            or self.allowed_company_ids != tuple(sorted(self.allowed_company_ids))
        ):
            raise ValueError
        if type(self.allow_runtime_models) is not bool:
            raise ValueError
        if self.lang is not None:
            _validate_text(self.lang, minimum=2, maximum=35)
        if (
            not isinstance(self.allowed_models, tuple)
            or not 1 <= len(self.allowed_models) <= 32
            or len(self.allowed_models) != len(set(self.allowed_models))
            or self.allowed_models != tuple(sorted(self.allowed_models))
            or any(not _MODEL_PATTERN.fullmatch(model) for model in self.allowed_models)
        ):
            raise ValueError
        if (
            not 1 <= len(self.scopes) <= len(ALLOWED_AGENT_SCOPES)
            or len(self.scopes) != len(set(self.scopes))
            or any(scope not in ALLOWED_AGENT_SCOPES for scope in self.scopes)
        ):
            raise ValueError
        if type(self.issued_at) is not int or type(self.expires_at) is not int:
            raise ValueError
        if not 0 < self.expires_at - self.issued_at <= MAX_AGENT_TTL_SECONDS:
            raise ValueError
        _validate_bounded_int(self.max_records, minimum=1, maximum=MAX_QUERY_RECORDS)
        _validate_bounded_int(self.max_fields, minimum=1, maximum=MAX_QUERY_RESULT_FIELDS)
        _validate_bounded_int(self.max_conditions, minimum=0, maximum=MAX_QUERY_CONDITIONS)
        _validate_bounded_int(self.max_groups, minimum=1, maximum=MAX_QUERY_GROUPS)
        _validate_bounded_int(self.max_aggregates, minimum=1, maximum=MAX_QUERY_AGGREGATES)
        _validate_bounded_int(self.max_write_steps, minimum=1, maximum=12)
        _validate_text(self.policy_revision, maximum=128)

    def to_mapping(self) -> dict[str, JsonValue]:
        return {
            "allowed_company_ids": list(self.allowed_company_ids),
            "allowed_models": list(self.allowed_models),
            "allow_runtime_models": self.allow_runtime_models,
            "company_id": self.company_id,
            "database": self.database,
            "expires_at": self.expires_at,
            "format_version": self.format_version,
            "issued_at": self.issued_at,
            "jti": self.jti,
            "lang": self.lang,
            "max_aggregates": self.max_aggregates,
            "max_conditions": self.max_conditions,
            "max_fields": self.max_fields,
            "max_groups": self.max_groups,
            "max_records": self.max_records,
            "max_write_steps": self.max_write_steps,
            "policy_revision": self.policy_revision,
            "scopes": list(self.scopes),
            "turn_id": str(self.turn_id),
            "uid": self.uid,
        }

    @classmethod
    def from_mapping(cls, raw: Mapping[str, object]) -> AgentDelegationPayload:
        expected = {
            "allowed_company_ids",
            "allowed_models",
            "allow_runtime_models",
            "company_id",
            "database",
            "expires_at",
            "format_version",
            "issued_at",
            "jti",
            "lang",
            "max_aggregates",
            "max_conditions",
            "max_fields",
            "max_groups",
            "max_records",
            "max_write_steps",
            "policy_revision",
            "scopes",
            "turn_id",
            "uid",
        }
        if set(raw) != expected:
            raise DelegationTokenError("invalid_agent_claims")
        try:
            version = _require_int(raw["format_version"])
            if version != AGENT_FORMAT_VERSION:
                raise DelegationTokenError("unknown_version")
            return cls(
                format_version=version,
                jti=_require_string(raw["jti"]),
                turn_id=UUID(_require_string(raw["turn_id"])),
                database=_require_string(raw["database"]),
                uid=_require_int(raw["uid"]),
                company_id=_require_int(raw["company_id"]),
                allowed_company_ids=tuple(_require_int_list(raw["allowed_company_ids"])),
                lang=_require_optional_string(raw["lang"]),
                allowed_models=tuple(_require_string_list(raw["allowed_models"])),
                allow_runtime_models=_require_bool(raw["allow_runtime_models"]),
                scopes=tuple(
                    cast(AgentDelegationScope, value)
                    for value in _require_string_list(raw["scopes"])
                ),
                issued_at=_require_int(raw["issued_at"]),
                expires_at=_require_int(raw["expires_at"]),
                max_records=_require_int(raw["max_records"]),
                max_fields=_require_int(raw["max_fields"]),
                max_conditions=_require_int(raw["max_conditions"]),
                max_groups=_require_int(raw["max_groups"]),
                max_aggregates=_require_int(raw["max_aggregates"]),
                max_write_steps=_require_int(raw["max_write_steps"]),
                policy_revision=_require_string(raw["policy_revision"]),
            )
        except DelegationTokenError:
            raise
        except (TypeError, ValueError) as error:
            raise DelegationTokenError("invalid_agent_claims") from error


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


class QueryDelegationCodec:
    """Canonical HMAC codec isolated from the legacy M2 v1 token family."""

    __slots__ = ("_clock", "_signing_key")

    def __init__(
        self,
        root_secret: bytes,
        *,
        clock: Callable[[], int] | None = None,
    ) -> None:
        if len(root_secret) < MIN_SECRET_BYTES:
            raise DelegationTokenError("signing_key_unavailable")
        self._signing_key = hmac.digest(root_secret, QUERY_KEY_PURPOSE, hashlib.sha256)
        self._clock = clock or _unix_time

    @classmethod
    def from_secret_file(
        cls,
        path: str | Path,
        *,
        clock: Callable[[], int] | None = None,
    ) -> QueryDelegationCodec:
        return cls(_read_secret_file(Path(path)), clock=clock)

    def encode(self, payload: QueryDelegationPayload) -> str:
        self._validate_time(payload)
        encoded_payload = _base64url_encode(_canonical_query_payload(payload))
        signed = f"{QUERY_TOKEN_PREFIX}.{encoded_payload}".encode("ascii")
        signature = hmac.digest(self._signing_key, signed, hashlib.sha256)
        return f"{QUERY_TOKEN_PREFIX}.{encoded_payload}.{_base64url_encode(signature)}"

    def decode(self, token: str) -> QueryDelegationPayload:
        try:
            encoded = token.encode("ascii")
        except (AttributeError, UnicodeEncodeError) as error:
            raise DelegationTokenError("malformed_token") from error
        if not encoded or len(encoded) > MAX_QUERY_TOKEN_BYTES:
            raise DelegationTokenError("malformed_token")
        parts = token.split(".")
        if len(parts) != 3:
            raise DelegationTokenError("malformed_token")
        prefix, encoded_payload, encoded_signature = parts
        if prefix != QUERY_TOKEN_PREFIX:
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
            raise DelegationTokenError("invalid_query_claims")
        payload = QueryDelegationPayload.from_mapping(cast(dict[str, object], loaded))
        if not hmac.compare_digest(_canonical_query_payload(payload), payload_bytes):
            raise DelegationTokenError("noncanonical_payload")
        self._validate_time(payload)
        return payload

    def _validate_time(self, payload: QueryDelegationPayload) -> None:
        now = self._clock()
        if type(now) is not int:
            raise DelegationTokenError("clock_unavailable")
        if payload.issued_at > now + MAX_CLOCK_SKEW_SECONDS:
            raise DelegationTokenError("not_yet_valid")
        if now >= payload.expires_at:
            raise DelegationTokenError("expired")


class ActionPreviewDelegationCodec:
    """Canonical HMAC codec isolated from both v1 reads and q1 queries."""

    __slots__ = ("_clock", "_signing_key")

    def __init__(
        self,
        root_secret: bytes,
        *,
        clock: Callable[[], int] | None = None,
    ) -> None:
        if len(root_secret) < MIN_SECRET_BYTES:
            raise DelegationTokenError("signing_key_unavailable")
        self._signing_key = hmac.digest(
            root_secret, ACTION_PREVIEW_KEY_PURPOSE, hashlib.sha256
        )
        self._clock = clock or _unix_time

    @classmethod
    def from_secret_file(
        cls,
        path: str | Path,
        *,
        clock: Callable[[], int] | None = None,
    ) -> ActionPreviewDelegationCodec:
        return cls(_read_secret_file(Path(path)), clock=clock)

    def encode(self, payload: ActionPreviewDelegationPayload) -> str:
        self._validate_time(payload)
        encoded_payload = _base64url_encode(_canonical_action_preview_payload(payload))
        signed = f"{ACTION_PREVIEW_TOKEN_PREFIX}.{encoded_payload}".encode("ascii")
        signature = hmac.digest(self._signing_key, signed, hashlib.sha256)
        return (
            f"{ACTION_PREVIEW_TOKEN_PREFIX}.{encoded_payload}."
            f"{_base64url_encode(signature)}"
        )

    def decode(self, token: str) -> ActionPreviewDelegationPayload:
        try:
            encoded = token.encode("ascii")
        except (AttributeError, UnicodeEncodeError) as error:
            raise DelegationTokenError("malformed_token") from error
        if not encoded or len(encoded) > MAX_QUERY_TOKEN_BYTES:
            raise DelegationTokenError("malformed_token")
        parts = token.split(".")
        if len(parts) != 3:
            raise DelegationTokenError("malformed_token")
        prefix, encoded_payload, encoded_signature = parts
        if prefix != ACTION_PREVIEW_TOKEN_PREFIX:
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
            raise DelegationTokenError("invalid_action_preview_claims")
        payload = ActionPreviewDelegationPayload.from_mapping(
            cast(dict[str, object], loaded)
        )
        if not hmac.compare_digest(
            _canonical_action_preview_payload(payload), payload_bytes
        ):
            raise DelegationTokenError("noncanonical_payload")
        self._validate_time(payload)
        return payload

    def _validate_time(self, payload: ActionPreviewDelegationPayload) -> None:
        now = self._clock()
        if type(now) is not int:
            raise DelegationTokenError("clock_unavailable")
        if payload.issued_at > now + MAX_CLOCK_SKEW_SECONDS:
            raise DelegationTokenError("not_yet_valid")
        if now >= payload.expires_at:
            raise DelegationTokenError("expired")


class AgentDelegationCodec:
    """Canonical HMAC codec isolated for unified multi-model agent turns."""

    __slots__ = ("_clock", "_signing_key")

    def __init__(
        self,
        root_secret: bytes,
        *,
        clock: Callable[[], int] | None = None,
    ) -> None:
        if len(root_secret) < MIN_SECRET_BYTES:
            raise DelegationTokenError("signing_key_unavailable")
        self._signing_key = hmac.digest(root_secret, AGENT_KEY_PURPOSE, hashlib.sha256)
        self._clock = clock or _unix_time

    @classmethod
    def from_secret_file(
        cls,
        path: str | Path,
        *,
        clock: Callable[[], int] | None = None,
    ) -> AgentDelegationCodec:
        return cls(_read_secret_file(Path(path)), clock=clock)

    def encode(self, payload: AgentDelegationPayload) -> str:
        self._validate_time(payload)
        encoded_payload = _base64url_encode(_canonical_agent_payload(payload))
        signed = f"{AGENT_TOKEN_PREFIX}.{encoded_payload}".encode("ascii")
        signature = hmac.digest(self._signing_key, signed, hashlib.sha256)
        return f"{AGENT_TOKEN_PREFIX}.{encoded_payload}.{_base64url_encode(signature)}"

    def decode(self, token: str) -> AgentDelegationPayload:
        try:
            encoded = token.encode("ascii")
        except (AttributeError, UnicodeEncodeError) as error:
            raise DelegationTokenError("malformed_token") from error
        if not encoded or len(encoded) > MAX_QUERY_TOKEN_BYTES:
            raise DelegationTokenError("malformed_token")
        parts = token.split(".")
        if len(parts) != 3:
            raise DelegationTokenError("malformed_token")
        prefix, encoded_payload, encoded_signature = parts
        if prefix != AGENT_TOKEN_PREFIX:
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
        if not isinstance(loaded, dict) or not all(isinstance(key, str) for key in loaded):
            raise DelegationTokenError("invalid_agent_claims")
        payload = AgentDelegationPayload.from_mapping(cast(dict[str, object], loaded))
        if not hmac.compare_digest(_canonical_agent_payload(payload), payload_bytes):
            raise DelegationTokenError("noncanonical_payload")
        self._validate_time(payload)
        return payload

    def _validate_time(self, payload: AgentDelegationPayload) -> None:
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


def _canonical_query_payload(payload: QueryDelegationPayload) -> bytes:
    return json.dumps(
        payload.to_mapping(),
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")


def _canonical_action_preview_payload(payload: ActionPreviewDelegationPayload) -> bytes:
    return json.dumps(
        payload.to_mapping(),
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")


def _canonical_agent_payload(payload: AgentDelegationPayload) -> bytes:
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


def _validate_bounded_int(value: int, *, minimum: int, maximum: int) -> None:
    if type(value) is not int or not minimum <= value <= maximum:
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


def _require_bool(value: object) -> bool:
    if type(value) is not bool:
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
