"""Cleanup for intervention rows that intentionally avoid a turn FK."""

from odoo import SUPERUSER_ID, models


class AssistantTurnInterventionCleanup(models.Model):
    _inherit = "odoo.ai.turn"

    def unlink(self):
        turn_ids = self.ids
        result = super().unlink()
        if turn_ids:
            self.env["odoo.ai.turn.intervention"].with_user(SUPERUSER_ID).search(
                [("turn_ref_id", "in", turn_ids)]
            ).unlink()
        return result
