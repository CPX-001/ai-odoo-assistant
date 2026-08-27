"""Private durable working transcript persistence for embedded agent turns."""

from __future__ import annotations

from odoo import SUPERUSER_ID, api, fields, models

from ..runtime.agent.working_transcript import (
    WorkingItem,
    load_working_transcript,
    transcript_payload,
)


class AssistantTurnWorkingTranscript(models.Model):
    _inherit = "odoo.ai.turn"

    working_items_payload = fields.Json(readonly=True, copy=False)

    @api.model
    def _working_items_from_turn(self, turn):
        return load_working_transcript(turn.working_items_payload)


def persist_working_transcript(
    turn,
    lease_token: str,
    items: tuple[WorkingItem, ...],
) -> None:
    """Commit private active-turn state on the primary worker cursor.

    Reasoning checkpoints are pre-effect boundaries. Committing them on the cursor that also owns
    pending activity events prevents a second cursor from updating ``odoo_ai_turn`` underneath a
    repeatable-read worker transaction.
    """

    payload = transcript_payload(items)
    technical = turn.with_user(SUPERUSER_ID).exists()
    technical.invalidate_recordset(["state", "lease_token"])
    if (
        not technical
        or technical.state != "running"
        or technical.lease_token != lease_token
    ):
        raise RuntimeError("agent_turn_lease_lost")
    technical.write(
        {
            "working_items_payload": payload,
            "heartbeat_at": fields.Datetime.now(),
        }
    )
    technical.env.cr.commit()
