"""Server-side identity derivation and scoped delegation preparation."""

from __future__ import annotations

import os
import secrets
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Final, Protocol
from uuid import UUID, uuid4

from ..security import DelegationCodec, DelegationPayload, DelegationTokenError
from .screen_context import (
    MAX_ODOO_ID,
    ValidatedScreenContext,
    validate_context_read_screen,
)

DELEGATION_SECRET_FILE_ENV: Final = "ODOO_AI_DELEGATION_SECRET_FILE"
DELEGATION_TTL_SECONDS: Final = 60
MAX_ACTIVE_COMPANIES: Final = 16
MAX_MESSAGE_LENGTH: Final = 4_000
DELEGATED_MAX_FIELDS: Final = 32


class _Record(Protocol):
    id: int


class _Records(Protocol):
    ids: list[int]


class _Cursor(Protocol):
    dbname: str


class OdooEnvironment(Protocol):
    """Small Odoo Environment surface required to derive current identity."""

    uid: int
    su: bool
    company: _Record
    companies: _Records
    lang: str
    cr: _Cursor

    def __contains__(self, model: object) -> bool: ...


class TurnContextError(RuntimeError):
    """Sanitized preparation failure safe to map at an Odoo controller."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class EffectiveUserContext:
    """Identity taken exclusively from the authenticated Odoo Environment."""

    uid: int
    company_id: int
    allowed_company_ids: tuple[int, ...]
    lang: str | None

    def to_mapping(self) -> dict[str, int | str | list[int] | None]:
        return {
            "allowed_company_ids": list(self.allowed_company_ids),
            "company_id": self.company_id,
            "lang": self.lang,
            "uid": self.uid,
        }


@dataclass(frozen=True, slots=True)
class PreparedContextTurn:
    """Server-only turn material; its delegation is redacted from repr/browser data."""

    turn_id: UUID
    message: str
    screen: ValidatedScreenContext
    user: EffectiveUserContext
    database: str
    delegation_token: str = field(repr=False)

    def to_assistant_payload(self) -> dict[str, object]:
        """Build the authenticated server-to-server body for a future M2 ingress."""

        return {
            "delegation_token": self.delegation_token,
            "gateway": {"database": self.database},
            "message": self.message,
            "screen": self.screen.to_mapping(),
            "turn_id": str(self.turn_id),
            "user": self.user.to_mapping(),
        }

    def to_browser_payload(self) -> dict[str, str]:
        """Return the only preparation result that a browser may observe."""

        return {"turn_id": str(self.turn_id)}


class TurnContextPreparer:
    """Create one short-lived delegation from an authenticated Odoo env."""

    def __init__(
        self,
        *,
        codec: DelegationCodec,
        clock: Callable[[], int] | None = None,
        turn_id_factory: Callable[[], UUID] | None = None,
        nonce_factory: Callable[[], str] | None = None,
    ) -> None:
        self._codec = codec
        self._clock = clock or _unix_time
        self._turn_id_factory = turn_id_factory or uuid4
        self._nonce_factory = nonce_factory or (lambda: secrets.token_urlsafe(18))

    def prepare(
        self,
        *,
        env: OdooEnvironment,
        screen_payload: Mapping[str, object],
        message: str,
    ) -> PreparedContextTurn:
        now = self._clock()
        if type(now) is not int:
            raise TurnContextError("clock_unavailable")
        screen = validate_context_read_screen(
            screen_payload,
            clock=lambda: datetime.fromtimestamp(now, UTC),
        )
        if screen.model not in env:
            raise TurnContextError("model_unavailable")
        normalized_message = _message(message)
        user = derive_user_execution_context(env)
        database = _database_binding(env)
        turn_id = self._turn_id_factory()
        if not isinstance(turn_id, UUID):
            raise TurnContextError("turn_id_unavailable")
        try:
            payload = DelegationPayload(
                format_version=1,
                jti=self._nonce_factory(),
                turn_id=turn_id,
                database=database,
                uid=user.uid,
                company_id=user.company_id,
                allowed_company_ids=user.allowed_company_ids,
                lang=user.lang,
                model=screen.model,
                record_ids=(screen.res_id,),
                scopes=("fields_get", "read_records"),
                issued_at=now,
                expires_at=now + DELEGATION_TTL_SECONDS,
                max_records=1,
                max_fields=DELEGATED_MAX_FIELDS,
            )
            token = self._codec.encode(payload)
        except DelegationTokenError as error:
            raise TurnContextError("delegation_unavailable") from error
        return PreparedContextTurn(
            turn_id=turn_id,
            message=normalized_message,
            screen=screen,
            user=user,
            database=database,
            delegation_token=token,
        )


def prepare_context_turn(
    *,
    env: OdooEnvironment,
    screen_payload: Mapping[str, object],
    message: str,
    secret_file: str | None = None,
    clock: Callable[[], int] | None = None,
) -> PreparedContextTurn:
    """Configured entrypoint for Odoo server code; no browser config is accepted."""

    resolved_secret_file = (
        secret_file or os.environ.get(DELEGATION_SECRET_FILE_ENV, "")
    ).strip()
    if not resolved_secret_file:
        raise TurnContextError("delegation_unconfigured")
    effective_clock = clock or _unix_time
    try:
        codec = DelegationCodec.from_secret_file(
            resolved_secret_file, clock=effective_clock
        )
    except DelegationTokenError:
        raise TurnContextError("delegation_unavailable") from None
    return TurnContextPreparer(codec=codec, clock=effective_clock).prepare(
        env=env,
        screen_payload=screen_payload,
        message=message,
    )


def derive_user_execution_context(env: OdooEnvironment) -> EffectiveUserContext:
    """Map Odoo 18 env identity/active companies/lang without browser claims."""

    if env.su:
        raise TurnContextError("superuser_delegation_forbidden")
    try:
        uid = _positive_id(env.uid)
        company_id = _positive_id(env.company.id)
        allowed_company_ids = tuple(_positive_id(value) for value in env.companies.ids)
        lang = env.lang
    except TurnContextError:
        raise
    except Exception:  # noqa: BLE001 - sanitize the Odoo environment boundary
        raise TurnContextError("identity_unavailable") from None
    if (
        not 1 <= len(allowed_company_ids) <= MAX_ACTIVE_COMPANIES
        or len(allowed_company_ids) != len(set(allowed_company_ids))
        or company_id not in allowed_company_ids
    ):
        raise TurnContextError("identity_unavailable")
    if lang is not None and (
        not isinstance(lang, str)
        or not 2 <= len(lang) <= 35
        or lang != lang.strip()
    ):
        raise TurnContextError("identity_unavailable")
    return EffectiveUserContext(
        uid=uid,
        company_id=company_id,
        allowed_company_ids=allowed_company_ids,
        lang=lang,
    )


def _message(value: object) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > MAX_MESSAGE_LENGTH:
        raise TurnContextError("invalid_message")
    return value


def _database_binding(env: OdooEnvironment) -> str:
    try:
        value = env.cr.dbname
    except Exception:  # noqa: BLE001 - sanitize the Odoo cursor boundary
        raise TurnContextError("database_unavailable") from None
    if (
        not isinstance(value, str)
        or not 1 <= len(value) <= 128
        or value != value.strip()
        or any(ord(character) < 32 for character in value)
    ):
        raise TurnContextError("database_unavailable")
    return value


def _positive_id(value: object) -> int:
    if type(value) is not int or not 1 <= value <= MAX_ODOO_ID:
        raise TurnContextError("identity_unavailable")
    return value


def _unix_time() -> int:
    return int(time.time())
