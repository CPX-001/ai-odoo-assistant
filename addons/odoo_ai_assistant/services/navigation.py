"""Bounded visible Odoo menu metadata for read-only HOW_TO evidence."""

import json
import re
import unicodedata
from datetime import datetime
from typing import Final

from odoo.exceptions import AccessError, MissingError

MAX_NAVIGATION_DEPTH: Final = 8
MAX_NAVIGATION_NODES: Final = 256
MAX_NAVIGATION_BYTES: Final = 128 * 1024
MAX_SOURCE_NODES: Final = 2_048
SUPPORTED_ACTION_TYPE: Final = "ir.actions.act_window"
SUPPORTED_VIEW_MODES: Final = frozenset(
    {"activity", "calendar", "form", "graph", "kanban", "list", "pivot"}
)

_MODEL_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]{0,127}$")

JsonValue = str | int | float | bool | list["JsonValue"] | dict[str, "JsonValue"] | None


class NavigationMetadataError(RuntimeError):
    """Sanitized visible-navigation collection failure."""

    def __init__(self, code: str, status: int) -> None:
        super().__init__(code)
        self.code = code
        self.status = status


def collect_visible_navigation(
    env: object,
    *,
    captured_at: datetime,
    max_depth: int = MAX_NAVIGATION_DEPTH,
    max_nodes: int = MAX_NAVIGATION_NODES,
    max_bytes: int = MAX_NAVIGATION_BYTES,
) -> dict[str, JsonValue]:
    """Use Odoo's native visible-menu computation and expose only a safe subset."""

    _validate_limits(max_depth=max_depth, max_nodes=max_nodes, max_bytes=max_bytes)
    try:
        raw = env["ir.ui.menu"].load_menus(False)
    except (AccessError, MissingError, KeyError, ValueError):
        raise NavigationMetadataError("access_denied", 403) from None
    if not isinstance(raw, dict) or not 1 <= len(raw) <= MAX_SOURCE_NODES:
        raise NavigationMetadataError("invalid_navigation", 502)
    root = raw.get("root")
    if not isinstance(root, dict):
        raise NavigationMetadataError("invalid_navigation", 502)

    nodes: list[JsonValue] = []
    visited: set[int] = set()
    truncated = False

    def visit(menu_id: int, *, parent_id: int | None, path: tuple[str, ...]) -> None:
        nonlocal truncated
        if menu_id in visited:
            raise NavigationMetadataError("invalid_navigation", 502)
        entry = raw.get(menu_id)
        if not isinstance(entry, dict):
            raise NavigationMetadataError("invalid_navigation", 502)
        visited.add(menu_id)
        label = _label(entry.get("name"))
        current_path = (*path, label)
        if len(current_path) > max_depth or len(nodes) >= max_nodes:
            truncated = True
            return
        sequence = _sequence(entry.get("sequence"))
        action = _action_summary(env, entry.get("action"))
        nodes.append(
            {
                "action": action,
                "label": label,
                "menu_id": menu_id,
                "parent_id": parent_id,
                "path": list(current_path),
                "sequence": sequence,
            }
        )
        for child_id in _ordered_children(raw, entry.get("children")):
            visit(child_id, parent_id=menu_id, path=current_path)

    for root_id in _ordered_children(raw, root.get("children")):
        visit(root_id, parent_id=None, path=())

    result: dict[str, JsonValue] = {
        "captured_at": _iso_datetime(captured_at),
        "content_trust": "untrusted",
        "limits": {
            "max_bytes": max_bytes,
            "max_depth": max_depth,
            "max_nodes": max_nodes,
        },
        "nodes": nodes,
        "ok": True,
        "truncated": truncated,
    }
    while _serialized_size(result) > max_bytes and nodes:
        nodes.pop()
        result["truncated"] = True
    if _serialized_size(result) > max_bytes:
        raise NavigationMetadataError("response_too_large", 413)
    return result


def _ordered_children(raw: dict[object, object], value: object) -> tuple[int, ...]:
    if not isinstance(value, list):
        raise NavigationMetadataError("invalid_navigation", 502)
    children: list[tuple[int, int]] = []
    seen: set[int] = set()
    for child_id in value:
        if type(child_id) is not int or child_id <= 0 or child_id in seen:
            raise NavigationMetadataError("invalid_navigation", 502)
        entry = raw.get(child_id)
        if not isinstance(entry, dict):
            raise NavigationMetadataError("invalid_navigation", 502)
        seen.add(child_id)
        sequence = _sequence(entry.get("sequence"))
        children.append((sequence if sequence is not None else 0, child_id))
    return tuple(child_id for _, child_id in sorted(children))


def _action_summary(env: object, value: object) -> dict[str, JsonValue] | None:
    if value in (None, False, ""):
        return None
    if not isinstance(value, str) or len(value) > 256:
        raise NavigationMetadataError("invalid_navigation", 502)
    action_type, separator, raw_id = value.partition(",")
    if not separator or action_type != SUPPORTED_ACTION_TYPE or not raw_id.isascii():
        return None
    try:
        action_id = int(raw_id)
    except ValueError:
        return None
    if action_id <= 0:
        return None
    summary: dict[str, JsonValue] = {
        "action_type": SUPPORTED_ACTION_TYPE,
        "target_model": None,
        "view_modes": [],
    }
    try:
        action = env[SUPPORTED_ACTION_TYPE].browse(action_id).exists()
        if len(action) != 1:
            return None
        action.check_access("read")
        target_model = action.res_model
        raw_modes = action.view_mode
    except (AccessError, MissingError, KeyError, ValueError):
        return summary
    if not isinstance(target_model, str) or not _MODEL_PATTERN.fullmatch(target_model):
        return summary
    if not isinstance(raw_modes, str) or not 1 <= len(raw_modes) <= 128:
        return summary
    modes = tuple(part.strip() for part in raw_modes.split(","))
    if (
        not 1 <= len(modes) <= len(SUPPORTED_VIEW_MODES)
        or len(modes) != len(set(modes))
        or any(mode not in SUPPORTED_VIEW_MODES for mode in modes)
    ):
        return summary
    summary["target_model"] = target_model
    summary["view_modes"] = list(modes)
    return summary


def _label(value: object) -> str:
    if not isinstance(value, str):
        raise NavigationMetadataError("invalid_navigation", 502)
    normalized = " ".join(unicodedata.normalize("NFKC", value).split())
    if not 1 <= len(normalized) <= 256 or len(normalized.encode("utf-8")) > 1_024:
        raise NavigationMetadataError("invalid_navigation", 502)
    return normalized


def _sequence(value: object) -> int | None:
    if value is False or value is None:
        return None
    if type(value) is not int or not -2_147_483_648 <= value <= 2_147_483_647:
        raise NavigationMetadataError("invalid_navigation", 502)
    return value


def _validate_limits(*, max_depth: int, max_nodes: int, max_bytes: int) -> None:
    if (
        type(max_depth) is not int
        or not 1 <= max_depth <= MAX_NAVIGATION_DEPTH
        or type(max_nodes) is not int
        or not 1 <= max_nodes <= MAX_NAVIGATION_NODES
        or type(max_bytes) is not int
        or not 512 <= max_bytes <= MAX_NAVIGATION_BYTES
    ):
        raise NavigationMetadataError("invalid_limits", 500)


def _serialized_size(value: dict[str, JsonValue]) -> int:
    try:
        return len(
            json.dumps(
                value,
                allow_nan=False,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        )
    except (TypeError, ValueError):
        raise NavigationMetadataError("invalid_navigation", 502) from None


def _iso_datetime(value: datetime) -> str:
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise NavigationMetadataError("invalid_navigation", 502)
    return value.isoformat().replace("+00:00", "Z")
