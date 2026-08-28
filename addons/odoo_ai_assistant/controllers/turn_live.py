"""Authenticated browser projection for persisted public activity and answer deltas."""

from __future__ import annotations

import logging

from odoo import http
from odoo.exceptions import AccessError, ValidationError
from odoo.http import request

_logger = logging.getLogger(__name__)


class AssistantTurnLiveController(http.Controller):
    @http.route(
        "/odoo_ai/v1/turn/live",
        type="json",
        auth="user",
        methods=["POST"],
    )
    def turn_live(self, turn_id=None, after_sequence=0, **unexpected):
        if unexpected:
            return _error("invalid_context")
        try:
            return request.env["odoo.ai.turn"].live_for_current_user(
                turn_id,
                after_sequence=after_sequence,
            )
        except (AccessError, ValidationError, ValueError, TypeError):
            return _error("turn_not_found")
        except Exception:  # noqa: BLE001
            _logger.exception("Assistant turn live projection failed")
            return _error("runtime_unavailable")


def _error(code):
    return {"ok": False, "error": {"code": code}}
