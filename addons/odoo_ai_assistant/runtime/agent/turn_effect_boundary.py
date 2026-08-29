"""Tiny host-owned serialization primitive for redirect/stop versus effect commit.

The lock is deliberately transaction-scoped and carries no business authority. It only orders the
last control-plane check against the durable write barrier so a late redirect/stop cannot race a
business effect into execution.
"""

from __future__ import annotations

import hashlib

_PERSON = b"odoo-ai-effect-v1"
_SIGN_BIT = 1 << 63
_UINT64 = 1 << 64


def turn_effect_lock_key(turn_uuid: str) -> int:
    """Return one stable signed PostgreSQL advisory-lock key for a persisted turn UUID."""

    if (
        not isinstance(turn_uuid, str)
        or not 1 <= len(turn_uuid) <= 128
        or "\x00" in turn_uuid
    ):
        raise ValueError("turn_effect_lock_key_invalid")
    digest = hashlib.blake2b(
        turn_uuid.encode("utf-8"),
        digest_size=8,
        person=_PERSON,
    ).digest()
    value = int.from_bytes(digest, byteorder="big", signed=False)
    return value - _UINT64 if value & _SIGN_BIT else value


def acquire_turn_effect_lock(cursor, turn_uuid: str) -> int:
    """Serialize one control/effect boundary until the caller's current transaction ends."""

    execute = getattr(cursor, "execute", None)
    if not callable(execute):
        raise ValueError("turn_effect_lock_cursor_invalid")
    key = turn_effect_lock_key(turn_uuid)
    execute("SELECT pg_advisory_xact_lock(%s)", [key])
    return key
