"""Browser routes for per-user semantic activity presentation preferences."""

from odoo import http
from odoo.http import request


class AssistantActivityPreferencesController(http.Controller):
    @http.route(
        "/odoo_ai/v1/activity-preferences",
        type="json",
        auth="user",
        methods=["POST"],
    )
    def activity_preferences(self, **unexpected):
        if unexpected:
            return _error("invalid_context")
        return request.env["odoo.ai.user.preference"].activity_presentation_preferences()

    @http.route(
        "/odoo_ai/v1/activity-preferences-set",
        type="json",
        auth="user",
        methods=["POST"],
    )
    def set_activity_preferences(self, preferences=None, **unexpected):
        if unexpected:
            return _error("invalid_context")
        return request.env[
            "odoo.ai.user.preference"
        ].set_activity_presentation_preferences(preferences)


def _error(code):
    return {"error": {"code": code}, "ok": False}
