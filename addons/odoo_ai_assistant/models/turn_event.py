"""Persisted, browser-safe progress events for Odoo-managed Assistant turns."""

from __future__ import annotations

import json
import re

from odoo import api, fields, models
from odoo.exceptions import ValidationError

_MAX_EVENT_PAYLOAD_BYTES = 16 * 1024
_MAX_EVENT_STRING = 2_048
_MAX_EVENT_ITEMS = 32
_MAX_EVENT_DEPTH = 6
_EVENT_TYPE = re.compile(r"^[a-z][a-z0-9_.:-]{0,63}$")
_DIAGNOSTIC_CODE = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
_SENSITIVE_KEY = re.compile(
    r"(?:auth|authorization|credential|password|prompt|secret|stderr|stdout|token)",
    re.IGNORECASE,
)


class AssistantTurnEvent(models.Model):
    _name = "odoo.ai.turn.event"
    _description = "Odoo AI Assistant Turn Event"
    _order = "turn_id, sequence"
    _log_access = False

    turn_id = fields.Many2one(
        "odoo.ai.turn",
        required=True,
        readonly=True,
        index=True,
        ondelete="cascade",
    )
    user_id = fields.Many2one(
        "res.users",
        related="turn_id.user_id",
        store=True,
        readonly=True,
        index=True,
    )
    company_id = fields.Many2one(
        "res.company",
        related="turn_id.company_id",
        store=True,
        readonly=True,
        index=True,
    )
    sequence = fields.Integer(required=True, readonly=True, index=True)
    event_type = fields.Char(required=True, readonly=True, index=True, size=64)
    title = fields.Char(required=True, readonly=True, size=256)
    payload = fields.Json(readonly=True)
    diagnostic_code = fields.Char(readonly=True, size=128)
    occurred_at = fields.Datetime(
        required=True,
        readonly=True,
        default=fields.Datetime.now,
        index=True,
    )

    _sql_constraints = [
        (
            "turn_sequence_unique",
            "unique(turn_id, sequence)",
            "Turn event sequence must be unique.",
        ),
    ]

    @api.model
    def append_for_turn(
        self,
        *,
        turn,
        event_type,
        title,
        payload=None,
        diagnostic_code=None,
    ):
        """Append one bounded event while the caller holds the turn row lock."""

        if not isinstance(event_type, str) or not _EVENT_TYPE.fullmatch(event_type):
            raise ValidationError("Invalid Assistant event type")
        normalized_title = _normalized_title(title)
        safe_payload = _sanitize_payload(payload or {}, depth=0)
        encoded = json.dumps(
            safe_payload,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        if len(encoded) > _MAX_EVENT_PAYLOAD_BYTES:
            raise ValidationError("Assistant event payload is too large")
        if diagnostic_code is not None and (
            not isinstance(diagnostic_code, str)
            or not _DIAGNOSTIC_CODE.fullmatch(diagnostic_code)
        ):
            raise ValidationError("Invalid Assistant diagnostic code")

        turn.ensure_one()
        sequence = int(turn.last_event_sequence or 0) + 1
        turn.write({"last_event_sequence": sequence})
        return self.create(
            {
                "turn_id": turn.id,
                "sequence": sequence,
                "event_type": event_type,
                "title": normalized_title,
                "payload": safe_payload,
                "diagnostic_code": diagnostic_code,
                "occurred_at": fields.Datetime.now(),
            }
        )

    def browser_view(self):
        self.ensure_one()
        return {
            "sequence": self.sequence,
            "type": self.event_type,
            "title": self.title,
            "payload": self.payload or {},
            "diagnostic_code": self.diagnostic_code or None,
            "occurred_at": _iso_utc(self.occurred_at),
        }


def _normalized_title(value):
    if not isinstance(value, str):
        raise ValidationError("Invalid Assistant event title")
    normalized = " ".join(value.split())
    if not 1 <= len(normalized) <= 256 or any(ord(char) < 32 for char in normalized):
        raise ValidationError("Invalid Assistant event title")
    return normalized


def _sanitize_payload(value, *, depth):
    if depth > _MAX_EVENT_DEPTH:
        raise ValidationError("Assistant event payload is too deep")
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value[:_MAX_EVENT_STRING]
    if isinstance(value, list):
        if len(value) > _MAX_EVENT_ITEMS:
            raise ValidationError("Assistant event payload has too many items")
        return [_sanitize_payload(item, depth=depth + 1) for item in value]
    if isinstance(value, dict):
        if len(value) > _MAX_EVENT_ITEMS or not all(
            isinstance(key, str) and 1 <= len(key) <= 128 for key in value
        ):
            raise ValidationError("Invalid Assistant event payload")
        return {
            key: _sanitize_payload(item, depth=depth + 1)
            for key, item in value.items()
            if not _SENSITIVE_KEY.search(key)
        }
    raise ValidationError("Invalid Assistant event payload")


def _iso_utc(value):
    if not value:
        return ""
    parsed = fields.Datetime.to_datetime(value)
    return parsed.replace(tzinfo=None).isoformat(timespec="microseconds") + "Z"
