"""Independent browser-safe activity and answer-delta persistence for Assistant turns.

Live rows intentionally do not have a foreign key to ``odoo.ai.turn``. A child FK insert can wait
on a worker-held turn-row lock, defeating pre-final visibility. The independent store copies only
the committed turn binding (integer id, UUID, user and company), serializes its own sequence with a
PostgreSQL advisory transaction lock and commits only its short live cursor. It never commits the
worker's business cursor, authorizes a capability, or changes write/recovery authority.
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
_MAX_RESOURCE_RECORDS = 50
_LIVE_LOCK_NAMESPACE = 20260828
_MODEL = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$")
_ACTIVITY_ID = re.compile(r"^activity:v[1-9][0-9]*:[0-9a-f]{32}$")
_DIAGNOSTIC = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")

_INTERNAL_ACTIVITY = {
    "started": ("turn.started", "queue", "running"),
    "reasoning.started": ("provider.connecting", "provider", "running"),
    "reasoning.completed": ("provider.connected", "provider", "completed"),
    "reasoning.failed": ("turn.failed", "provider", "failed"),
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
    _order = "turn_ref_id, sequence"
    _log_access = False

    # No FK to odoo.ai.turn: see module docstring and P3-REAL-LIVE-VISIBILITY.
    turn_ref_id = fields.Integer(required=True, readonly=True, index=True)
    turn_uuid = fields.Char(required=True, readonly=True, index=True, size=64)
    user_id = fields.Many2one("res.users", required=True, readonly=True, index=True)
    company_id = fields.Many2one("res.company", required=True, readonly=True, index=True)
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
    references = fields.Json(readonly=True)
    semantic = fields.Json(readonly=True)
    capability = fields.Char(readonly=True, size=128)
    activity_id = fields.Char(readonly=True, size=64, index=True)
    progress = fields.Integer(readonly=True)
    progress_set = fields.Boolean(readonly=True, default=False)
    diagnostic_code = fields.Char(readonly=True, size=128)
    answer_delta = fields.Text(readonly=True)
    occurred_at = fields.Datetime(
        required=True,
        readonly=True,
        default=fields.Datetime.now,
        index=True,
    )

    _sql_constraints = [
        (
            "turn_live_sequence_unique",
            "unique(turn_ref_id, sequence)",
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
        references=None,
        capability=None,
        activity_id=None,
        progress=None,
        diagnostic_code=None,
        semantic=None,
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
            references=references or (),
            capability=capability,
            activity_id=activity_id,
            progress=progress,
            diagnostic_code=diagnostic_code,
            semantic=semantic,
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
                turn_id=self.turn_uuid,
                kind=self.kind,
                phase=self.phase,
                status=self.status,
                label=self.label,
                resource=self.resource or None,
                references=tuple(self.references or ()),
                capability=self.capability or None,
                progress=self.progress if self.progress_set else None,
                diagnostic_code=self.diagnostic_code or None,
                occurred_at=_iso_utc(self.occurred_at),
                activity_id=self.activity_id or None,
                semantic=self.semantic or None,
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
        if (
            not isinstance(text, str)
            or not 1 <= len(text) <= _MAX_ANSWER_DELTA
            or "\x00" in text
        ):
            raise ValidationError("Invalid persisted Assistant answer delta")
        return {
            "sequence": self.sequence,
            "channel": "answer",
            "turn_id": self.turn_uuid,
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
            if (
                diagnostic_code is not None
                or not isinstance(payload, dict)
                or set(payload) != {"text"}
            ):
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
                "kind",
                "phase",
                "status",
                "label",
                "resource",
                "capability",
                "progress",
                "diagnostic_code",
            }
            optional = {"activity_id", "references"}
            optional.add("semantic")
            if not expected.issubset(payload) or set(payload) - expected - optional:
                raise ValidationError("Invalid Assistant public-activity bridge")
            normalized = dict(payload)
            normalized.setdefault("activity_id", None)
            normalized.setdefault("references", [])
            normalized.setdefault("semantic", None)
            self.env["odoo.ai.turn.live.event"].append_activity_independent(
                turn_id=turn.id,
                **normalized,
            )
            return self.browse()

        # Project before the historical event mutates ``turn.last_event_sequence`` on the worker
        # cursor. With no FK this is non-blocking even when other business fields are already dirty.
        projection = _public_projection(event_type, title, payload, diagnostic_code)
        if projection is not None:
            try:
                self.env["odoo.ai.turn.live.event"].append_activity_independent(
                    turn_id=turn.id,
                    **projection,
                )
            except Exception:  # noqa: BLE001 - public UX never controls business success
                pass
        return super().append_for_turn(
            turn=turn,
            event_type=event_type,
            title=title,
            payload=payload,
            diagnostic_code=diagnostic_code,
        )

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
        if type(after_sequence) is not int or after_sequence < 0:
            raise ValidationError("Invalid Assistant public-activity cursor")
        turn = self._owned_turn(turn_uuid)
        rows = self.env["odoo.ai.turn.live.event"].search(
            [
                ("turn_ref_id", "=", turn.id),
                ("turn_uuid", "=", turn.turn_uuid),
                ("channel", "=", "activity"),
                ("sequence", ">", after_sequence),
            ],
            order="sequence",
            limit=_MAX_LIVE_PAGE + 1,
        )
        has_more = len(rows) > _MAX_LIVE_PAGE
        page = rows[:_MAX_LIVE_PAGE]
        return {
            "events": [row.activity_browser_view() for row in page],
            "last_sequence": page[-1].sequence if page else after_sequence,
            "has_more": has_more,
        }

    @api.model
    def live_for_current_user(self, turn_uuid, *, after_sequence=0):
        if type(after_sequence) is not int or after_sequence < 0:
            raise ValidationError("Invalid Assistant live-event cursor")
        turn = self._owned_turn(turn_uuid)
        rows = self.env["odoo.ai.turn.live.event"].search(
            [
                ("turn_ref_id", "=", turn.id),
                ("turn_uuid", "=", turn.turn_uuid),
                ("sequence", ">", after_sequence),
            ],
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
    activity_id = data.get("activity_id")
    if not isinstance(activity_id, str) or _ACTIVITY_ID.fullmatch(activity_id) is None:
        activity_id = None
    code = diagnostic_code or data.get("code")
    if not isinstance(code, str) or _DIAGNOSTIC.fullmatch(code) is None:
        code = None
    references = data.get("references") if isinstance(data.get("references"), list) else []
    return {
        "kind": kind,
        "phase": phase,
        "status": status,
        "label": title,
        "resource": _resource_from_payload(data),
        "references": references,
        "capability": capability,
        "activity_id": activity_id,
        "progress": None,
        "diagnostic_code": code,
        "semantic": data.get("semantic"),
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
    record_ids = [
        item
        for item in record_ids[:_MAX_RESOURCE_RECORDS]
        if type(item) is int and item > 0
    ]
    names = payload.get("display_names")
    if not isinstance(names, list) or len(names) != len(record_ids):
        names = []
    return {"model": model, "record_ids": record_ids, "display_names": names}


def _append_activity(dbname, *, turn_id, **data):
    with _live_cursor(dbname, turn_id) as (cr, env, binding, sequence):
        occurred_at = fields.Datetime.now()
        try:
            event = PublicTurnEvent(
                sequence=sequence,
                turn_id=binding["turn_uuid"],
                occurred_at=_iso_utc(occurred_at),
                **data,
            )
        except (PublicTurnEventError, TypeError) as error:
            raise ValidationError("Invalid Assistant public activity") from error
        record = env["odoo.ai.turn.live.event"].create(
            {
                **_binding_values(binding),
                "sequence": sequence,
                "channel": "activity",
                "kind": event.kind,
                "phase": event.phase,
                "status": event.status,
                "label": event.label,
                "resource": event.resource or False,
                "references": [dict(item) for item in event.references] or False,
                "capability": event.capability or False,
                "activity_id": event.activity_id or False,
                "progress": event.progress if event.progress is not None else 0,
                "progress_set": event.progress is not None,
                "diagnostic_code": event.diagnostic_code or False,
                "semantic": event.semantic or False,
                "occurred_at": occurred_at,
            }
        )
        result = record.activity_browser_view()
        cr.commit()
        return result


def _append_answer(dbname, *, turn_id, text):
    if not isinstance(text, str) or "\x00" in text:
        raise ValidationError("Invalid Assistant answer delta")
    if not 1 <= len(text) <= _MAX_ANSWER_DELTA:
        raise ValidationError("Assistant answer delta budget exceeded")
    with _live_cursor(dbname, turn_id) as (cr, env, binding, sequence):
        if binding["state"] != "running":
            raise ValidationError("Assistant answer delta requires a running turn")
        live = env["odoo.ai.turn.live.event"]
        domain = [
            ("turn_ref_id", "=", binding["turn_ref_id"]),
            ("turn_uuid", "=", binding["turn_uuid"]),
            ("channel", "=", "answer"),
        ]
        previous = live.search(domain, order="sequence", limit=_MAX_LIVE_EVENTS)
        total = sum(len(row.answer_delta or "") for row in previous)
        if total + len(text) > _MAX_ANSWER_CHARS:
            raise ValidationError("Assistant answer-delta budget exceeded")

        if not previous:
            started_at = fields.Datetime.now()
            started = PublicTurnEvent(
                sequence=sequence,
                turn_id=binding["turn_uuid"],
                kind="agent.answer.started",
                phase="answer",
                status="running",
                label="Redactando respuesta",
                resource=None,
                references=(),
                capability=None,
                progress=None,
                diagnostic_code=None,
                occurred_at=_iso_utc(started_at),
                activity_id=None,
                semantic=None,
            )
            live.create(
                {
                    **_binding_values(binding),
                    "sequence": sequence,
                    "channel": "activity",
                    "kind": started.kind,
                    "phase": started.phase,
                    "status": started.status,
                    "label": started.label,
                    "resource": False,
                    "references": False,
                    "capability": False,
                    "activity_id": False,
                    "progress": 0,
                    "progress_set": False,
                    "diagnostic_code": False,
                    "semantic": False,
                    "occurred_at": started_at,
                }
            )
            sequence += 1
            if sequence > _MAX_LIVE_EVENTS:
                raise ValidationError("Assistant live-event budget exceeded")

        record = live.create(
            {
                **_binding_values(binding),
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
        binding = {
            "turn_ref_id": turn.id,
            "turn_uuid": turn.turn_uuid,
            "user_id": turn.user_id.id,
            "company_id": turn.company_id.id,
            "state": turn.state,
        }
        if (
            not isinstance(binding["turn_uuid"], str)
            or not binding["turn_uuid"]
            or type(binding["user_id"]) is not int
            or binding["user_id"] <= 0
            or type(binding["company_id"]) is not int
            or binding["company_id"] <= 0
        ):
            raise ValidationError("Invalid Assistant live-event binding")
        live = env["odoo.ai.turn.live.event"]
        last = live.search(
            [
                ("turn_ref_id", "=", turn.id),
                ("turn_uuid", "=", turn.turn_uuid),
            ],
            order="sequence desc",
            limit=1,
        )
        sequence = (last.sequence if last else 0) + 1
        if sequence > _MAX_LIVE_EVENTS:
            raise ValidationError("Assistant live-event budget exceeded")
        yield cr, env, binding, sequence


def _binding_values(binding):
    return {
        "turn_ref_id": binding["turn_ref_id"],
        "turn_uuid": binding["turn_uuid"],
        "user_id": binding["user_id"],
        "company_id": binding["company_id"],
    }


def _require_live_writer(env):
    if env.uid != SUPERUSER_ID:
        raise AccessError("Assistant live-event writes are host-internal only")


def _iso_utc(value):
    if not value:
        return ""
    parsed = fields.Datetime.to_datetime(value)
    return parsed.replace(tzinfo=None).isoformat(timespec="microseconds") + "Z"
