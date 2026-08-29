"""Late browser projection for verified effect compensation metadata."""

from odoo import SUPERUSER_ID, models

from .turn_control import _plan_with_reversion_state


class EmbeddedAssistantTurnControlProjection(models.AbstractModel):
    _inherit = "odoo.ai.embedded.runtime"

    def _plan_response(self, turn, envelope, policy, *, completed=False):
        response = super()._plan_response(turn, envelope, policy, completed=completed)
        plan = envelope.get("plan") if isinstance(envelope, dict) else None
        state = turn.reversion_state or "none"
        if (
            isinstance(plan, dict)
            and plan.get("state") == "completed"
            and state == "none"
        ):
            state = self._plan_reversion_state(turn, plan, policy)
            turn.with_user(SUPERUSER_ID).write({"reversion_state": state})
        if isinstance(response.get("plan"), dict):
            response["plan"] = _plan_with_reversion_state(response["plan"], state)
        return response
