"""Browser-safe readable reasoning-summary deltas.

Only provider-declared readable summaries enter this channel. Raw/private reasoning is never
accepted here. The rows share the independent live cursor used by activity/answer streaming so
reconnect ordering remains deterministic without committing the business cursor.
"""

from __future__ import annotations

import re

from odoo import api, fields, models
from odoo.exceptions import ValidationError

from .turn_live_event import (
    _binding_values,
    _iso_utc,
    _live_cursor,
    _require_live_writer,
)

_MAX_REASONING_DELTA = 2 * 1024
_MAX_REASONING_TOTAL = 8 * 1024
_MAX_REASONING_INDEX = 64
_REASONING_ITEM_ID = re.compile(r"^[A-Za-z0-9_.:-]{1,256}$")


class AssistantTurnLiveReasoningSummary(models.Model):
    _inherit = "odoo.ai.turn.live.event"

    channel = fields.Selection(
        selection_add=[("reasoning", "Reasoning summary")],
        ondelete={"reasoning": "cascade"},
    )
    reasoning_summary_delta = fields.Text(readonly=True)
    reasoning_item_id = fields.Char(readonly=True, size=256)
    reasoning_summary_index = fields.Integer(readonly=True)

    def live_browser_view(self):
        self.ensure_one()
        if self.channel != "reasoning":
            return super().live_browser_view()
        text = self.reasoning_summary_delta
        if (
            not isinstance(text, str)
            or not 1 <= len(text) <= _MAX_REASONING_DELTA
            or "\x00" in text
            or not isinstance(self.reasoning_item_id, str)
            or _REASONING_ITEM_ID.fullmatch(self.reasoning_item_id) is None
            or type(self.reasoning_summary_index) is not int
            or not 0 <= self.reasoning_summary_index <= _MAX_REASONING_INDEX
        ):
            raise ValidationError("Invalid persisted Assistant reasoning summary")
        return {
            "sequence": self.sequence,
            "channel": "reasoning",
            "turn_id": self.turn_uuid,
            "item_id": self.reasoning_item_id,
            "summary_index": self.reasoning_summary_index,
            "text": text,
            "occurred_at": _iso_utc(self.occurred_at),
        }

    @api.model
    def append_reasoning_summary_independent(
        self,
        *,
        turn_id,
        item_id,
        summary_index,
        text,
    ):
        _require_live_writer(self.env)
        return _append_reasoning_summary(
            self.env.cr.dbname,
            turn_id=turn_id,
            item_id=item_id,
            summary_index=summary_index,
            text=text,
        )


class AssistantTurnEventReasoningBridge(models.Model):
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
        if event_type != "reasoning.summary.delta":
            return super().append_for_turn(
                turn=turn,
                event_type=event_type,
                title=title,
                payload=payload,
                diagnostic_code=diagnostic_code,
            )
        if (
            diagnostic_code is not None
            or not isinstance(payload, dict)
            or set(payload) != {"item_id", "summary_index", "text"}
        ):
            raise ValidationError("Invalid Assistant reasoning-summary bridge")
        self.env["odoo.ai.turn.live.event"].append_reasoning_summary_independent(
            turn_id=turn.id,
            item_id=payload["item_id"],
            summary_index=payload["summary_index"],
            text=payload["text"],
        )
        return self.browse()


def _append_reasoning_summary(dbname, *, turn_id, item_id, summary_index, text):
    if (
        not isinstance(item_id, str)
        or _REASONING_ITEM_ID.fullmatch(item_id) is None
        or type(summary_index) is not int
        or not 0 <= summary_index <= _MAX_REASONING_INDEX
        or not isinstance(text, str)
        or not 1 <= len(text) <= _MAX_REASONING_DELTA
        or "\x00" in text
    ):
        raise ValidationError("Invalid Assistant reasoning summary")
    with _live_cursor(dbname, turn_id) as (cr, env, binding, sequence):
        if binding["state"] != "running":
            raise ValidationError("Assistant reasoning summary requires a running turn")
        live = env["odoo.ai.turn.live.event"]
        domain = [
            ("turn_ref_id", "=", binding["turn_ref_id"]),
            ("turn_uuid", "=", binding["turn_uuid"]),
            ("channel", "=", "reasoning"),
        ]
        previous = live.search(domain, order="sequence", limit=1024)
        total = sum(len(row.reasoning_summary_delta or "") for row in previous)
        if total + len(text) > _MAX_REASONING_TOTAL:
            raise ValidationError("Assistant reasoning-summary budget exceeded")
        record = live.create(
            {
                **_binding_values(binding),
                "sequence": sequence,
                "channel": "reasoning",
                "reasoning_summary_delta": text,
                "reasoning_item_id": item_id,
                "reasoning_summary_index": summary_index,
                "occurred_at": fields.Datetime.now(),
            }
        )
        result = record.live_browser_view()
        cr.commit()
        return result
