"""Browser endpoints for current-turn stop, redirect and explicit safe compensation."""

from odoo import http
from odoo.exceptions import AccessError, ValidationError
from odoo.http import request

from ..models.turn_control import TurnControlError


class AssistantTurnControlController(http.Controller):
    @http.route("/odoo_ai/v1/turn/redirect", type="json", auth="user", methods=["POST"])
    def redirect_turn(
        self,
        turn_id=None,
        message=None,
        client_intervention_id=None,
        **unexpected,
    ):
        if unexpected:
            return _error("invalid_context")
        try:
            return request.env["odoo.ai.turn"].redirect_for_current_user(
                turn_id,
                message,
                client_intervention_id=client_intervention_id,
            )
        except AccessError:
            return _error("turn_not_found")
        except ValidationError:
            return _error("invalid_context")
        except TurnControlError as error:
            return _error(error.code)

    @http.route("/odoo_ai/v1/turn/revert", type="json", auth="user", methods=["POST"])
    def revert_turn(self, turn_id=None, **unexpected):
        if unexpected:
            return _error("invalid_context")
        try:
            return request.env["odoo.ai.turn"].revert_for_current_user(turn_id)
        except AccessError:
            return _error("turn_not_found")
        except ValidationError:
            return _error("invalid_context")
        except TurnControlError as error:
            return _error(error.code)


def _error(code):
    return {"ok": False, "error": {"code": code}}
