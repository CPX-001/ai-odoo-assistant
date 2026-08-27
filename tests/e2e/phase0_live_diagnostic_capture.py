#!/usr/bin/env python3
"""Phase 0 live capture with extra content-free diagnostics for provider/action debugging.

This wrapper reuses the authoritative Phase 0 HTTP capture and changes only event sanitization.
It may retain installed capability identifiers plus bounded planning checkpoint metadata. It still
drops prompts, answers, capability arguments/results, business values, credentials and provider
stdout/stderr.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path
from typing import Any

_BASE_PATH = Path(__file__).with_name("phase0_live_capture.py")
_SPEC = importlib.util.spec_from_file_location("phase0_live_capture_base", _BASE_PATH)
assert _SPEC is not None and _SPEC.loader is not None
base = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(base)
_BASE_SAFE_EVENT = base._safe_event

_CAPABILITY = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]{0,127}$")
_TOKEN = re.compile(r"^[a-z0-9_]{1,64}$")
_COUNT_KEYS = frozenset(
    {
        "reasoning_tool_count",
        "planning_tool_count",
        "staged_plan_count",
        "structured_plan_count",
        "final_plan_count",
    }
)


def _safe_capability(value: Any) -> str | None:
    return value if isinstance(value, str) and _CAPABILITY.fullmatch(value) else None


def _safe_planning_payload(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    point = value.get("point")
    if not isinstance(point, str) or _TOKEN.fullmatch(point) is None:
        return None
    safe: dict[str, Any] = {"point": point}
    capability = _safe_capability(value.get("capability"))
    if capability is not None:
        safe["capability"] = capability
    source = value.get("source")
    if isinstance(source, str) and _TOKEN.fullmatch(source):
        safe["source"] = source
    for key in _COUNT_KEYS:
        count = value.get(key)
        if type(count) is int and 0 <= count <= 32:
            safe[key] = count
    return safe


def _safe_event(event: Any) -> dict[str, Any] | None:
    safe = _BASE_SAFE_EVENT(event)
    if safe is None or not isinstance(event, dict):
        return safe
    event_type = event.get("type")
    payload = event.get("payload")
    if event_type == "diagnostic.planning":
        planning = _safe_planning_payload(payload)
        if planning is not None:
            safe["payload"] = planning
    elif isinstance(event_type, str) and event_type.startswith("tool.") and isinstance(payload, dict):
        capability = _safe_capability(payload.get("capability"))
        if capability is not None:
            safe["payload"] = {"capability": capability}
    return safe


base._safe_event = _safe_event
main = base.main


if __name__ == "__main__":
    raise SystemExit(main())
