"""One-shot planning input for newly enqueued Assistant turns."""

from __future__ import annotations

from odoo import api, models
from odoo.exceptions import ValidationError

_ONE_SHOT_PLANNING_MODES = frozenset({"adaptive", "deliberate"})
_PLANNING_CONTEXT_KEY = "assistant_planning_mode_override"


class AssistantTurnOneShotPlanning(models.Model):
    _inherit = "odoo.ai.turn"

    @api.model
    def enqueue_for_current_user(
        self,
        *,
        message,
        screen,
        conversation_uuid=None,
        client_request_id=None,
        planning_mode="adaptive",
    ):
        """Capture planning for this turn only; never mutate a user preference."""

        if planning_mode not in _ONE_SHOT_PLANNING_MODES:
            raise ValidationError("Invalid Assistant planning mode")
        return super(
            AssistantTurnOneShotPlanning,
            self.with_context(**{_PLANNING_CONTEXT_KEY: planning_mode}),
        ).enqueue_for_current_user(
            message=message,
            screen=screen,
            conversation_uuid=conversation_uuid,
            client_request_id=client_request_id,
        )
