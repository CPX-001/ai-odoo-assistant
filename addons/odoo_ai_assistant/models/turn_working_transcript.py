"""Private durable working transcript persistence for embedded agent turns."""

from __future__ import annotations

from odoo import SUPERUSER_ID, api, fields, models
from odoo.modules.registry import Registry

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
    dbname: str,
    turn_id: int,
    lease_token: str,
    items: tuple[WorkingItem, ...],
) -> None:
    """Commit private active-turn state without changing business authority."""

    payload = transcript_payload(items)
    with Registry(dbname).cursor() as cr:
        env = api.Environment(cr, SUPERUSER_ID, {}, su=True)
        turn = env["odoo.ai.turn"].browse(turn_id).exists()
        if not turn or turn.state != "running" or turn.lease_token != lease_token:
            raise RuntimeError("agent_turn_lease_lost")
        turn.write({"working_items_payload": payload, "heartbeat_at": fields.Datetime.now()})
        cr.commit()
