"""Browser projection for the provider-neutral, non-authoritative TaskPlan."""

from __future__ import annotations

from odoo import SUPERUSER_ID, api, models

from ..runtime.agent.task_plan import TaskPlanError, parse_task_plan
from ..runtime.agent.working_transcript import WorkingTranscriptError
from .embedded_runtime import EmbeddedRuntimeError


class EmbeddedAssistantTaskPlanProjection(models.AbstractModel):
    _inherit = "odoo.ai.embedded.runtime"

    @api.model
    def run_turn(self, *, turn_id, lease_token):
        """Add only the latest host-validated TaskPlan to the public turn response.

        The projection runs above the provider-specific adapter and cannot execute capabilities.
        During an approval wait the enriched response is persisted so reconnect/history paths see
        the same TaskPlan. Running-turn live TaskPlan projection is deliberately left to the
        deliberate-mode UX work instead of overloading the public activity contract here.
        """

        response = super().run_turn(turn_id=turn_id, lease_token=lease_token)
        if not isinstance(response, dict):
            return response

        turn = self.env["odoo.ai.turn"].browse(turn_id).exists()
        if not turn:
            raise EmbeddedRuntimeError("agent_turn_lease_lost")
        task_plan = _latest_task_plan_payload(turn)
        enriched = {**response, "task_plan": task_plan}

        turn.invalidate_recordset(["state", "result_payload"])
        if turn.state == "awaiting_confirmation":
            stored = turn.result_payload
            if not isinstance(stored, dict):
                raise EmbeddedRuntimeError("capability_plan_corrupt")
            turn.with_user(SUPERUSER_ID).write(
                {"result_payload": {**stored, "task_plan": task_plan}}
            )
        return enriched


def _latest_task_plan_payload(turn):
    try:
        items = turn._working_items_from_turn(turn)
    except WorkingTranscriptError as error:
        raise EmbeddedRuntimeError(error.code) from error
    for item in reversed(items):
        if item.kind != "task_plan":
            continue
        try:
            return parse_task_plan(dict(item.data)).payload()
        except TaskPlanError as error:
            raise EmbeddedRuntimeError(error.code) from error
    return None
