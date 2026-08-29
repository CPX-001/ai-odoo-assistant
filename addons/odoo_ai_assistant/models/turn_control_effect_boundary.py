"""Serialize browser Stop/redirect requests with the effect write barrier."""

from odoo import api, models

from ..runtime.agent.turn_effect_boundary import acquire_turn_effect_lock


class AssistantTurnEffectBoundaryControl(models.Model):
    _inherit = "odoo.ai.turn"

    @api.model
    def redirect_for_current_user(
        self,
        turn_uuid,
        message,
        client_intervention_id=None,
    ):
        turn = self._owned_turn(turn_uuid)
        acquire_turn_effect_lock(self.env.cr, turn.turn_uuid)
        return super().redirect_for_current_user(
            turn_uuid,
            message,
            client_intervention_id=client_intervention_id,
        )

    @api.model
    def cancel_for_current_user(self, turn_uuid):
        turn = self._owned_turn(turn_uuid)
        acquire_turn_effect_lock(self.env.cr, turn.turn_uuid)
        return super().cancel_for_current_user(turn_uuid)
