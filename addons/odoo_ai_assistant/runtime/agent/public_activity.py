"""Dependency-light closed contracts for Phase 3/P5.8 public Assistant activity."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TypeAlias

JsonObject: TypeAlias = dict[str, object]

PUBLIC_EVENT_KINDS = frozenset(
    {
        "turn.queued",
        "turn.started",
        "provider.connecting",
        "provider.connected",
        "agent.answer.started",
        "capability.started",
        "capability.completed",
        "capability.failed",
        "retrieval.started",
        "retrieval.completed",
        "preview.started",
        "preview.completed",
        "approval.required",
        "execution.started",
        "execution.completed",
        "verification.started",
        "verification.completed",
        "turn.completed",
        "turn.failed",
        "turn.cancelled",
    }
)
PUBLIC_EVENT_PHASES = frozenset(
    {
        "queue",
        "provider",
        "answer",
        "capability",
        "retrieval",
        "preview",
        "approval",
        "execution",
        "verification",
        "finalization",
    }
)
PUBLIC_EVENT_STATUSES = frozenset(
    {"pending", "running", "completed", "failed", "blocked", "cancelled"}
)

_TURN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{7,127}$")
_MODEL_RE = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$")
_FIELD_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")
_CAPABILITY_RE = _MODEL_RE
_ACTIVITY_ID_RE = re.compile(r"^activity:v[1-9][0-9]*:[0-9a-f]{32}$")
_DIAGNOSTIC_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
_OCCURRED_AT_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z$"
)
_MAX_LABEL = 240
_MAX_RESOURCE_RECORDS = 50
_MAX_DISPLAY_NAME = 160
_MAX_NAVIGATION_REFERENCES = 12
_NAVIGATION_KINDS = frozenset(
    {"odoo_model", "odoo_action", "odoo_view", "odoo_menu", "odoo_setting"}
)


class PublicTurnEventError(RuntimeError):
    def __init__(self, code: str = "public_turn_event_invalid") -> None:
        super().__init__(code)
        self.code = code


def _one_line(value: object, *, maximum: int, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise PublicTurnEventError()
    normalized = " ".join(value.split())
    if (not normalized and not allow_empty) or len(normalized) > maximum or "\x00" in normalized:
        raise PublicTurnEventError()
    return normalized


def _resource(value: object) -> JsonObject | None:
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) != {
        "model",
        "record_ids",
        "display_names",
    }:
        raise PublicTurnEventError()
    model = value.get("model")
    record_ids = value.get("record_ids")
    display_names = value.get("display_names")
    if model is not None and (
        not isinstance(model, str) or _MODEL_RE.fullmatch(model) is None
    ):
        raise PublicTurnEventError()
    if (
        not isinstance(record_ids, list)
        or len(record_ids) > _MAX_RESOURCE_RECORDS
        or any(type(record_id) is not int or record_id <= 0 for record_id in record_ids)
        or len(set(record_ids)) != len(record_ids)
    ):
        raise PublicTurnEventError()
    if (
        not isinstance(display_names, list)
        or len(display_names) > _MAX_RESOURCE_RECORDS
        or any(not isinstance(name, str) for name in display_names)
    ):
        raise PublicTurnEventError()
    normalized_names = tuple(
        _one_line(name, maximum=_MAX_DISPLAY_NAME) for name in display_names
    )
    if normalized_names and len(normalized_names) != len(record_ids):
        raise PublicTurnEventError()
    if (record_ids or normalized_names) and model is None:
        raise PublicTurnEventError()
    return {
        "model": model,
        "record_ids": list(record_ids),
        "display_names": list(normalized_names),
    }


def _navigation_reference(value: object) -> JsonObject:
    if not isinstance(value, dict):
        raise PublicTurnEventError()
    kind = value.get("kind")
    if kind not in _NAVIGATION_KINDS:
        raise PublicTurnEventError()
    label = _one_line(value.get("label"), maximum=160)
    description = _one_line(value.get("description"), maximum=240, allow_empty=True)
    if kind == "odoo_model":
        expected = {"kind", "label", "description", "model"}
    elif kind == "odoo_action":
        expected = {"kind", "label", "description", "model", "action_id"}
    elif kind == "odoo_view":
        expected = {"kind", "label", "description", "model", "view_id"}
    elif kind == "odoo_menu":
        expected = {
            "kind",
            "label",
            "description",
            "model",
            "action_id",
            "menu_id",
        }
    else:
        expected = {
            "kind",
            "label",
            "description",
            "model",
            "action_id",
            "setting_field",
        }
    if set(value) != expected:
        raise PublicTurnEventError()
    model = value.get("model")
    if not isinstance(model, str) or _MODEL_RE.fullmatch(model) is None:
        raise PublicTurnEventError()
    result: JsonObject = {
        "kind": kind,
        "label": label,
        "description": description,
        "model": model,
    }
    for key in ("action_id", "view_id", "menu_id"):
        if key not in value:
            continue
        item = value.get(key)
        if type(item) is not int or item <= 0:
            raise PublicTurnEventError()
        result[key] = item
    if "setting_field" in value:
        field = value.get("setting_field")
        if not isinstance(field, str) or _FIELD_RE.fullmatch(field) is None:
            raise PublicTurnEventError()
        result["setting_field"] = field
    if kind == "odoo_setting" and model != "res.config.settings":
        raise PublicTurnEventError()
    return result


def _references(value: object) -> tuple[JsonObject, ...]:
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)) or len(value) > _MAX_NAVIGATION_REFERENCES:
        raise PublicTurnEventError()
    return tuple(_navigation_reference(item) for item in value)


@dataclass(frozen=True, slots=True)
class PublicTurnEvent:
    sequence: int
    turn_id: str
    kind: str
    phase: str
    status: str
    label: str
    resource: JsonObject | None
    capability: str | None
    progress: int | None
    diagnostic_code: str | None
    occurred_at: str
    activity_id: str | None = None
    references: tuple[JsonObject, ...] = ()

    def __post_init__(self) -> None:
        if type(self.sequence) is not int or self.sequence <= 0:
            raise PublicTurnEventError()
        if not isinstance(self.turn_id, str) or _TURN_ID_RE.fullmatch(self.turn_id) is None:
            raise PublicTurnEventError()
        if self.kind not in PUBLIC_EVENT_KINDS or self.kind == "agent.thinking":
            raise PublicTurnEventError()
        if self.phase not in PUBLIC_EVENT_PHASES:
            raise PublicTurnEventError()
        if self.status not in PUBLIC_EVENT_STATUSES:
            raise PublicTurnEventError()
        object.__setattr__(self, "label", _one_line(self.label, maximum=_MAX_LABEL))
        object.__setattr__(self, "resource", _resource(self.resource))
        object.__setattr__(self, "references", _references(self.references))
        if self.capability is not None and (
            not isinstance(self.capability, str)
            or _CAPABILITY_RE.fullmatch(self.capability) is None
        ):
            raise PublicTurnEventError()
        if self.progress is not None and (
            type(self.progress) is not int or not 0 <= self.progress <= 100
        ):
            raise PublicTurnEventError()
        if self.diagnostic_code is not None and (
            not isinstance(self.diagnostic_code, str)
            or _DIAGNOSTIC_RE.fullmatch(self.diagnostic_code) is None
        ):
            raise PublicTurnEventError()
        if (
            not isinstance(self.occurred_at, str)
            or _OCCURRED_AT_RE.fullmatch(self.occurred_at) is None
        ):
            raise PublicTurnEventError()
        if self.activity_id is not None and (
            not isinstance(self.activity_id, str)
            or _ACTIVITY_ID_RE.fullmatch(self.activity_id) is None
        ):
            raise PublicTurnEventError()


@dataclass(frozen=True, slots=True)
class PublicCapabilityActivityDescriptor:
    """Trusted installed-code labels prepared for CapabilityDefinition wiring."""

    started_label: str
    completed_label: str
    failed_label: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "started_label",
            _one_line(self.started_label, maximum=_MAX_LABEL),
        )
        object.__setattr__(
            self,
            "completed_label",
            _one_line(self.completed_label, maximum=_MAX_LABEL),
        )
        object.__setattr__(
            self,
            "failed_label",
            _one_line(self.failed_label, maximum=_MAX_LABEL),
        )


def parse_public_turn_event(value: object) -> PublicTurnEvent:
    keys = {
        "sequence",
        "turn_id",
        "kind",
        "phase",
        "status",
        "label",
        "resource",
        "capability",
        "progress",
        "diagnostic_code",
        "occurred_at",
        "activity_id",
        "references",
    }
    if not isinstance(value, dict) or set(value) != keys:
        raise PublicTurnEventError()
    try:
        return PublicTurnEvent(**value)
    except (KeyError, TypeError):
        raise PublicTurnEventError() from None


def public_turn_event_payload(event: PublicTurnEvent) -> JsonObject:
    if not isinstance(event, PublicTurnEvent):
        raise PublicTurnEventError()
    resource = None
    if event.resource is not None:
        resource = {
            "model": event.resource["model"],
            "record_ids": list(event.resource["record_ids"]),
            "display_names": list(event.resource["display_names"]),
        }
    return {
        "sequence": event.sequence,
        "turn_id": event.turn_id,
        "kind": event.kind,
        "phase": event.phase,
        "status": event.status,
        "label": event.label,
        "resource": resource,
        "capability": event.capability,
        "progress": event.progress,
        "diagnostic_code": event.diagnostic_code,
        "occurred_at": event.occurred_at,
        "activity_id": event.activity_id,
        "references": [dict(item) for item in event.references],
    }


def validate_event_batch(
    value: object,
    *,
    after_sequence: int = 0,
    maximum: int = 100,
) -> tuple[PublicTurnEvent, ...]:
    if (
        type(after_sequence) is not int
        or after_sequence < 0
        or not 1 <= maximum <= 100
        or not isinstance(value, list)
        or len(value) > maximum
    ):
        raise PublicTurnEventError()
    events = tuple(parse_public_turn_event(item) for item in value)
    previous = after_sequence
    turn_id = None
    for event in events:
        if event.sequence <= previous:
            raise PublicTurnEventError("public_turn_event_order_invalid")
        if turn_id is None:
            turn_id = event.turn_id
        elif event.turn_id != turn_id:
            raise PublicTurnEventError("public_turn_event_turn_mismatch")
        previous = event.sequence
    return events
