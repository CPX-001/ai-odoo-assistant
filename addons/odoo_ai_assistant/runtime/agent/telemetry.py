"""Fail-soft helpers for optional agent lifecycle telemetry."""

from __future__ import annotations


def emit_optional_telemetry(context, event_type, title, payload=None) -> bool:
    """Emit one diagnostic event without letting telemetry control the turn outcome.

    ``CapabilityContext.emit`` owns transaction restoration.  This boundary deliberately
    catches only ``Exception`` so process cancellation and other ``BaseException`` signals
    continue to propagate.
    """

    cursor = getattr(getattr(context, "env", None), "cr", None)
    flush = getattr(cursor, "flush", None)
    if callable(flush):
        # A failure in already-pending authoritative state is not a telemetry failure.
        # Flush it before entering the fail-soft boundary so it remains visible upstream.
        flush()
    try:
        context.emit(event_type, title, payload)
    except Exception:  # noqa: BLE001 - optional telemetry is never product authority
        return False
    return True
