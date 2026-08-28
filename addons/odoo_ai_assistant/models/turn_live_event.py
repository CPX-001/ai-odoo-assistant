"""Independent browser-safe activity and answer-delta persistence for Assistant turns.

Live rows use their own short cursor/transaction. They never commit the worker's business cursor,
authorize a capability, or change write/recovery authority.
"""

from __future__ import annotations

import re
from contextlib import contextmanager

from odoo import SUPERUSER_ID, api, fields, models
from odoo.exceptions import AccessError, ValidationError
from odoo.modules.registry import Registry

from ..runtime.agent.public_activity import (
    PublicTurnEvent,
    PublicTurnEventError,
    public_turn_event_payload,
)

_MAX_LIVE_EVENTS = 1024
_MAX_LIVE_PAGE = 100
_MAX_ANSWER_CHARS = 16 * 1024
_MAX_ANSWER_DELTA = 2 * 1024
_LIVE_LOCK_NAMESPACE = 20260828
_MODEL = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$")
_DIAGNOSTIC = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")

_INTERNAL_ACTIVITY = {
    "started": ("turn.started", "queue", "running"),
    "reasoning.started": ("provider.connecting", "provider", "running"),
    "tool.started": ("capability.started", "capability", "running"),
    "tool.completed": ("capability.completed", "capability", "completed"),
    "tool.failed": ("capability.failed", "capability", "failed"),
    "tool.preview.started": ("preview.started", "preview", "running"),
    "tool.preview.completed": ("preview.completed", "preview", "completed"),
    "approval.required": ("approval.required", "approval", "blocked"),
    "execution.barrier": ("execution.started", "execution", "running"),
    "tool.verify.started": ("verification.started", "verification", "running"),
    "tool.verify.completed": ("verification.completed", "verification", "completed"),
    "completed": ("turn.completed", "finalization", "completed"),
    "failed": ("turn.failed", "finalization", "failed"),
    "recovery_required": ("turn.failed", "finalization", "failed"),
    "cancelled": ("turn.cancelled", "finalization", "cancelled"),
}


class AssistantTurnLiveEvent(models.Model):
    _name = "odoo.ai.turn.live.event"
    _description = "Odoo AI Assistant Browser-safe Live Event"
    _order = "turn_id, sequence"
    _log_access = False

    turn_id = fields.Many2one(
        "odoo.ai.turn", required=True, readonly=True, index=True, ondelete="cascade"
    )
    user_id = fields.Many2one(
        "res.users", related="turn_id.user_id", store=True, readonly=True, index=True
    )
    company_id = fields.Many2one(
        "res.company", related="turn_id.company_id", store=True, readonly=True, index=True
    )
    sequence = fields.Integer(required=True, readonly=True, index=True)
    channel = fields.Selection(
        [("activity", "Activity"), ("answer", "Answer")],
        required=True,
        readonly=True,
        index=True,
    )
    kind = fields.Char(readonly=True, size=64)
    phase = fields.Char(readonly=True, size=32)
    status = fields.Char(readonly=True, size=32)
    label = fields.Char(readonly=True, size=240)
    resource = fields.Json(readonly=True)
    capability = fields.Char(readonly=True, size=128)
    progress = fields.Integer(readonly=True)
    progress_set = fields.Boolean(readonly=True, default=False)
    diagnostic_code = fields.Char(readonly=True, size=128)
    answer_delta = fields.Text(readonly=True)
    occurred_at = fields.Datetime(required=True, readonly=True, default=fields.Datetime.now, index=True)

    _sql_constraints = [
        (
            "turn_live_sequence_unique",
            "unique(turn_id, sequence)",
            "Assistant live-event sequence must be unique.",
        ),
    ]

    @api.model
    def append_activity_independent(
        self,
        *,
        turn_id,
        kind,
        phase,
        status,
        label,
        resource=None,
        capability=None,
        progress=None,
        diagnostic_code=None,
    ):
        _require_live_writer(self.env)
        return _append_activity(
            self.env.cr.dbname,
            turn_id=turn_id,
            kind=kind,
            phase=phase,
            status=status,
            label=label,
            resource=resource,
            capability=capability,
            progress=progress,
            diagnostic_code=diagnostic_code,
        )

    @api.model
    def append_answer_delta_independent(self, *, turn_id, text):
        _require_live_writer(self.env)
        return _append_answer(self.env.cr.dbname, turn_id=turn_id, text=text)

    def activity_browser_view(self):
        self.ensure_one()
        if self.channel != "activity":
            raise ValidationError("Assistant live event is not public activity")
        try:
            event = PublicTurnEvent(
                sequence=self.sequence,
                turn_id=self.turn_id.turn_uuid,
                kind=self.kind,
                phase=self.phase,
                status=self.status,
                label=self.label,
                resource=self.resource or None,
                capability=self.capability or None,
                progress=self.progress if self.progress_set else None,
                diagnostic_code=self.diagnostic_code or None,
                occurred_at=_iso_utc(self.occurred_at),
            )
        except PublicTurnEventError as error:
            raise ValidationError("Invalid persisted Assistant public activity") from error
        return public_turn_event_payload(event)

    def live_browser_view(self):
        self.ensure_one()
        if self.channel == "activity":
            return {
                "sequence": self.sequence,
                "channel": "activity",
                "event": self.activity_browser_view(),
            }
        text = self.answer_delta
        if not isinstance(text, str) or not 1 <= len(text) <= _MAX_ANSWER_DELTA or "\x00" in text:
            raise ValidationError("Invalid persisted Assistant answer delta")
        return {
            "sequence": self.sequence,
            "channel": "answer",
            "turn_id": self.turn_id.turn_uuid,
            "text": text,
            "occurred_at": _iso_utc(self.occurred_at),
        }


class AssistantTurnEventLiveBridge(models.Model):
    _inherit = "odoo.ai.turn.event"

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
        if event_type == "answer.delta":
            if diagnostic_code is not None or not isinstance(payload, dict) or set(payload) != {"text"}:
                raise ValidationError("Invalid Assistant answer-delta bridge")
            self.env["odoo.ai.turn.live.event"].append_answer_delta_independent(
                turn_id=turn.id,
                text=payload["text"],
            )
            return self.browse()
        if event_type == "public.activity":
            if diagnostic_code is not None or not isinstance(payload, dict):
                raise ValidationError("Invalid Assistant public-activity bridge")
            expected = {
                "kind", "phase", "status", "label", "resource", "capability",
                "progress", "diagnostic_code",
            }
            if set(payload) != expected:
                raise ValidationError("Invalid Assistant public-activity bridge")
            self.env["odoo.ai.turn.live.event"].append_activity_independent(
                turn_id=turn.id,
                **payload,
            )
            return self.browse()

        record = super().append_for_turn(
            turn=turn,
            event_type=event_type,
            title=title,
            payload=payload,
            diagnostic_code=diagnostic_code,
        )
        projection = _public_projection(event_type, title, payload, diagnostic_code)
        if projection is not None:
            try:
                self.env["odoo.ai.turn.live.event"].append_activity_independent(
                    turn_id=turn.id,
                    **projection,
                )
            except Exception:  # noqa: BLE001 - public UX never controls business success
                pass
        return record

    @api.model
    def append_public_independent(self, *, turn_id, **values):
        """Closed compatibility API used by the Phase 3 acceptance harness."""
        return self.env["odoo.ai.turn.live.event"].append_activity_independent(
            turn_id=turn_id,
            **values,
        )


class AssistantTurnLiveProjection(models.Model):
    _inherit = "odoo.ai.turn"

    @api.model
    def public_events_for_current_user(self, turn_uuid, *, after_sequence=0):
        payload = self.live_for_current_user(turn_uuid, after_sequence=after_sequence)
        events = [item["event"] for item in payload["items"] if item["channel"] == "activity"]
        last = max((event["sequence"] for event in events), default=after_sequence)
        return {"events": events, "last_sequence": last, "has_more": payload["has_more"]}

    @api.model
    def live_for_current_user(self, turn_uuid, *, after_sequence=0):
        if type(after_sequence) is not int or after_sequence < 0:
            raise ValidationError("Invalid Assistant live-event cursor")
        turn = self._owned_turn(turn_uuid)
        rows = self.env["odoo.ai.turn.live.event"].search(
            [("turn_id", "=", turn.id), ("sequence", ">", after_sequence)],
            order="sequence",
            limit=_MAX_LIVE_PAGE + 1,
        )
        has_more = len(rows) > _MAX_LIVE_PAGE
        page = rows[:_MAX_LIVE_PAGE]
        return {
            "ok": True,
            "turn_id": turn.turn_uuid,
            "items": [row.live_browser_view() for row in page],
            "last_sequence": page[-1].sequence if page else after_sequence,
            "has_more": has_more,
        }


def _public_projection(event_type, title, payload, diagnostic_code):
    mapping = _INTERNAL_ACTIVITY.get(event_type)
    if mapping is None:
        return None
    kind, phase, status = mapping
    data = payload if isinstance(payload, dict) else {}
    capability = data.get("capability")
    if not isinstance(capability, str) or _MODEL.fullmatch(capability) is None:
        capability = None
    code = diagnostic_code or data.get("code")
    if not isinstance(code, str) or _DIAGNOSTIC.fullmatch(code) is None:
        code = None
    return {
        "kind": kind,
        "phase": phase,
        "status": status,
        "label": title,
        "resource": _resource_from_payload(data),
        "capability": capability,
        "progress": None,
        "diagnostic_code": code,
    }


def _resource_from_payload(payload):
    model = payload.get("model")
    if not isinstance(model, str) or _MODEL.fullmatch(model) is None:
        return None
    record_ids = payload.get("record_ids")
    if record_ids is None and type(payload.get("record_id")) is int:
        record_ids = [payload["record_id"]]
    if not isinstance(record_ids, list):
        record_ids = []
    record_ids = [item for item in record_ids[:20] if type(item) is int and item > 0]
    names = payload.get("display_names")
    if not isinstance(names, list) or len(names) != len(record_ids):
        names = []
    return {"model": model, "record_ids": record_ids, "display_names": names}


def _append_activity(dbname, *, turn_id, **data):
    with _live_cursor(dbname, turn_id) as (cr, env, turn, sequence):
        occurred_at = fields.Datetime.now()
        try:
            event = PublicTurnEvent(
                sequence=sequence,
                turn_id=turn.turn_uuid,
                occurred_at=_iso_utc(occurred_at),
                **data,
            )
        except (PublicTurnEventError, TypeError) as error:
            raise ValidationError("Invalid Assistant public activity") from error
        record = env["odoo.ai.turn.live.event"].create(
            {
                "turn_id": turn.id,
                "sequence": sequence,
                "channel": "activity",
                "kind": event.kind,
                "phase": event.phase,
                "status": event.status,
                "label": event.label,
                "resource": event.resource or False,
                "capability": event.capability or False,
                "progress": event.progress if event.progress is not None else 0,
                "progress_set": event.progress is not None,
                "diagnostic_code": event.diagnostic_code or False,
                "occurred_at": occurred_at,
            }
        )
        result = record.activity_browser_view()
        cr.commit()
        return result


def _append_answer(dbname, *, turn_id, text):
    if not isinstance(text, str) or not 1 <= len(text) <= _MAX_ANSWER_DELTA or "\x00" in text:
        raise ValidationError("Invalid Assistant answer delta")
    with _live_cursor(dbname, turn_id) as (cr, env, turn, sequence):
        if turn.state != "running":
            raise ValidationError("Assistant answer delta requires a running turn")
        live = env["odoo.ai.turn.live.event"]
        previous = live.search(
            [("turn_id", "=", turn.id), ("channel", "=", "answer")],
            order="sequence",
            limit=_MAX_LIVE_EVENTS,
        )
        total = sum(len(row.answer_delta or "") for row in previous)
        if total + len(text) > _MAX_ANSWER_CHARS:
            raise ValidationError("Assistant answer-delta budget exceeded")

        if not previous:
            started_at = fields.Datetime.now()
            started = PublicTurnEvent(
                sequence=sequence,
                turn_id=turn.turn_uuid,
                kind="agent.answer.started",
                phase="answer",
                status="running",
                label="Redactando respuesta",
                resource=None,
                capability=None,
                progress=None,
                diagnostic_code=None,
                occurred_at=_iso_utc(started_at),
            )
            live.create(
                {
                    "turn_id": turn.id,
                    "sequence": sequence,
                    "channel": "activity",
                    "kind": started.kind,
                    "phase": started.phase,
                    "status": started.status,
                    "label": started.label,
                    "resource": False,
                    "capability": False,
                    "progress": 0,
                    "progress_set": False,
                    "diagnostic_code": False,
                    "occurred_at": started_at,
                }
            )
            sequence += 1
            if sequence > _MAX_LIVE_EVENTS:
                raise ValidationError("Assistant live-event budget exceeded")

        record = live.create(
            {
                "turn_id": turn.id,
                "sequence": sequence,
                "channel": "answer",
                "answer_delta": text,
                "occurred_at": fields.Datetime.now(),
            }
        )
        result = record.live_browser_view()
        cr.commit()
        return result


@contextmanager
def _live_cursor(dbname, turn_id):
    if type(turn_id) is not int or turn_id <= 0:
        raise ValidationError("Invalid Assistant live-event turn")
    with Registry(dbname).cursor() as cr:
        cr.execute("SELECT pg_advisory_xact_lock(%s, %s)", [_LIVE_LOCK_NAMESPACE, turn_id])
        env = api.Environment(cr, SUPERUSER_ID, {}, su=True)
        turn = env["odoo.ai.turn"].browse(turn_id).exists()
        if not turn:
            raise ValidationError("Assistant live-event turn not found")
        live = env["odoo.ai.turn.live.event"]
        last = live.search([("turn_id", "=", turn.id)], order="sequence desc", limit=1)
        sequence = (last.sequence if last else 0) + 1
        if sequence > _MAX_LIVE_EVENTS:
            raise ValidationError("Assistant live-event budget exceeded")
        yield cr, env, turn, sequence


def _require_live_writer(env):
    if env.uid != SUPERUSER_ID:
        raise AccessError("Assistant live-event writes are host-internal only")


def _iso_utc(value):
    if not value:
        return ""
    parsed = fields.Datetime.to_datetime(value)
    return parsed.replace(tzinfo=None).isoformat(timespec="microseconds") + "Z"
