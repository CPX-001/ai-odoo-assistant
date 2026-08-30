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
        """Add the latest host-validated TaskPlan to the terminal/approval response.

        Terminal response shape stays backward-compatible with the already accepted browser response
        contract. Running status may expose the newer revision metadata separately.
        """

        response = super().run_turn(turn_id=turn_id, lease_token=lease_token)
        if not isinstance(response, dict):
            return response

        turn = self.env["odoo.ai.turn"].browse(turn_id).exists()
        if not turn:
            raise EmbeddedRuntimeError("agent_turn_lease_lost")
        task_plan = _latest_task_plan_payload(turn, include_revision_metadata=False)
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


class AssistantTurnTaskPlanStatusProjection(models.Model):
    _inherit = "odoo.ai.turn"

    def browser_status(self, *, after_sequence=0):
        """Expose validated TaskPlan progress while a turn is still running.

        This is public progress data only. Capability arguments, results and private reasoning remain in the
        host working transcript and are never copied into this status projection.
        """

        self.ensure_one()
        response = super().browser_status(after_sequence=after_sequence)
        response["task_plan"] = _latest_task_plan_payload(self, include_revision_metadata=True)
        return response


def _latest_task_plan_payload(turn, *, include_revision_metadata):
    try:
        items = turn._working_items_from_turn(turn)
    except WorkingTranscriptError as error:
        raise EmbeddedRuntimeError(error.code) from error
    for item in reversed(items):
        if item.kind != "task_plan":
            continue
        try:
            payload = parse_task_plan(dict(item.data)).payload()
        except TaskPlanError as error:
            raise EmbeddedRuntimeError(error.code) from error
        if include_revision_metadata:
            return payload
        return {
            "goal": payload["goal"],
            "revision": payload["revision"],
            "steps": payload["steps"],
        }
    return None
