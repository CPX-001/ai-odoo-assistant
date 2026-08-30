"""Keep the Phase 6 EffectJournal aligned with verified P5.8 compensation."""

from odoo import SUPERUSER_ID, api, models


class AssistantEffectJournalReversion(models.Model):
    _inherit = "odoo.ai.turn"

    @api.model
    def revert_for_current_user(self, turn_uuid):
        result = super().revert_for_current_user(turn_uuid)
        turn = self._owned_turn(turn_uuid)
        self.env["odoo.ai.effect.journal"].with_user(SUPERUSER_ID)._mark_reverted(turn)
        return result
