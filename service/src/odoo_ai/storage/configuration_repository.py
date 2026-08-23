"""Atomic persistence for bounded M7 runtime configuration revisions."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, cast

from pydantic import JsonValue
from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Integer,
    MetaData,
    String,
    Table,
    func,
    insert,
    select,
    update,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session

_metadata = MetaData()

_runtime_config_state = Table(
    "runtime_config_state",
    _metadata,
    Column("id", Integer, primary_key=True),
    Column("current_revision", Integer, nullable=False),
    Column("current_fingerprint", String(64)),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

_runtime_config_revision = Table(
    "runtime_config_revision",
    _metadata,
    Column("revision", Integer, primary_key=True),
    Column("fingerprint", String(64), nullable=False),
    Column("overrides", JSONB, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

_runtime_config_audit_event = Table(
    "runtime_config_audit_event",
    _metadata,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("revision", Integer, nullable=False),
    Column("event_type", String(64), nullable=False),
    Column("actor_uid", Integer, nullable=False),
    Column("actor_database", String(128), nullable=False),
    Column("changed_keys", JSONB, nullable=False),
    Column("fingerprint", String(64), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)


class RuntimeConfigStoreError(RuntimeError):
    """Sanitized persistence failure for runtime configuration state."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class LockedRuntimeConfiguration:
    """Current revision read while holding the singleton state row lock."""

    revision: int
    fingerprint: str | None
    overrides: dict[str, JsonValue]


def read_runtime_configuration(
    session: Session,
    *,
    for_update: bool = False,
) -> LockedRuntimeConfiguration:
    """Read the current last-known-good revision, optionally locking it for apply."""

    statement = select(
        _runtime_config_state.c.current_revision,
        _runtime_config_state.c.current_fingerprint,
    ).where(_runtime_config_state.c.id == 1)
    if for_update:
        statement = statement.with_for_update()
    state = session.execute(statement).mappings().one_or_none()
    if state is None:
        raise RuntimeConfigStoreError("configuration_state_missing")

    revision = state["current_revision"]
    fingerprint = state["current_fingerprint"]
    if type(revision) is not int or revision < 0:
        raise RuntimeConfigStoreError("configuration_state_invalid")
    if fingerprint is not None and (
        not isinstance(fingerprint, str)
        or len(fingerprint) != 64
        or any(character not in "0123456789abcdef" for character in fingerprint)
    ):
        raise RuntimeConfigStoreError("configuration_state_invalid")
    if revision == 0:
        if fingerprint is not None:
            raise RuntimeConfigStoreError("configuration_state_invalid")
        return LockedRuntimeConfiguration(revision=0, fingerprint=None, overrides={})

    row = session.execute(
        select(
            _runtime_config_revision.c.fingerprint,
            _runtime_config_revision.c.overrides,
        ).where(_runtime_config_revision.c.revision == revision)
    ).mappings().one_or_none()
    if row is None or row["fingerprint"] != fingerprint:
        raise RuntimeConfigStoreError("configuration_revision_missing")
    return LockedRuntimeConfiguration(
        revision=revision,
        fingerprint=cast(str, fingerprint),
        overrides=_json_mapping(row["overrides"]),
    )


def persist_runtime_configuration(
    session: Session,
    *,
    locked: LockedRuntimeConfiguration,
    overrides: Mapping[str, JsonValue],
    fingerprint: str,
    actor_uid: int,
    actor_database: str,
    changed_keys: Sequence[str],
) -> LockedRuntimeConfiguration:
    """Append one valid revision and advance the singleton pointer in one transaction."""

    if len(fingerprint) != 64 or any(
        character not in "0123456789abcdef" for character in fingerprint
    ):
        raise RuntimeConfigStoreError("configuration_fingerprint_invalid")
    if actor_uid <= 0 or not actor_database or len(actor_database) > 128:
        raise RuntimeConfigStoreError("configuration_actor_invalid")
    if any(not key or len(key) > 128 for key in changed_keys):
        raise RuntimeConfigStoreError("configuration_audit_invalid")

    next_revision = locked.revision + 1
    serialized_overrides = dict(overrides)
    session.execute(
        insert(_runtime_config_revision).values(
            revision=next_revision,
            fingerprint=fingerprint,
            overrides=serialized_overrides,
        )
    )
    result = cast(
        CursorResult[Any],
        session.execute(
            update(_runtime_config_state)
            .where(
                _runtime_config_state.c.id == 1,
                _runtime_config_state.c.current_revision == locked.revision,
            )
            .values(
                current_revision=next_revision,
                current_fingerprint=fingerprint,
                updated_at=func.clock_timestamp(),
            )
        )
    )
    if result.rowcount != 1:
        raise RuntimeConfigStoreError("configuration_revision_conflict")
    session.execute(
        insert(_runtime_config_audit_event).values(
            revision=next_revision,
            event_type="configuration_applied",
            actor_uid=actor_uid,
            actor_database=actor_database,
            changed_keys=list(changed_keys),
            fingerprint=fingerprint,
        )
    )
    session.flush()
    return LockedRuntimeConfiguration(
        revision=next_revision,
        fingerprint=fingerprint,
        overrides=_json_mapping(serialized_overrides),
    )


def list_runtime_config_audit_events(
    session: Session,
    *,
    limit: int = 50,
) -> tuple[dict[str, JsonValue], ...]:
    """Return sanitized audit facts; values/secrets are intentionally absent."""

    if not 1 <= limit <= 200:
        raise ValueError("configuration audit limit must be between 1 and 200")
    rows = session.execute(
        select(
            _runtime_config_audit_event.c.revision,
            _runtime_config_audit_event.c.event_type,
            _runtime_config_audit_event.c.actor_uid,
            _runtime_config_audit_event.c.actor_database,
            _runtime_config_audit_event.c.changed_keys,
            _runtime_config_audit_event.c.fingerprint,
        )
        .order_by(_runtime_config_audit_event.c.id.desc())
        .limit(limit)
    ).mappings()
    events: list[dict[str, JsonValue]] = []
    for row in rows:
        changed = row["changed_keys"]
        if not isinstance(changed, list) or any(not isinstance(key, str) for key in changed):
            raise RuntimeConfigStoreError("configuration_audit_invalid")
        events.append(
            {
                "revision": cast(int, row["revision"]),
                "event_type": cast(str, row["event_type"]),
                "actor_uid": cast(int, row["actor_uid"]),
                "actor_database": cast(str, row["actor_database"]),
                "changed_keys": cast(list[JsonValue], changed),
                "fingerprint": cast(str, row["fingerprint"]),
            }
        )
    return tuple(events)


def _json_mapping(value: object) -> dict[str, JsonValue]:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise RuntimeConfigStoreError("configuration_payload_invalid")
    return cast(dict[str, JsonValue], value)
