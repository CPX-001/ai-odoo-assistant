"""Browser route for revalidated typed Assistant references."""

from odoo import http
from odoo.http import request


class AssistantPublicReferencesController(http.Controller):
    @http.route(
        "/odoo_ai/v1/public-references",
        type="json",
        auth="user",
        methods=["POST"],
    )
    def public_references(self, references=None, **unexpected):
        if unexpected:
            return _error("invalid_context")
        return request.env["odoo.ai.user.preference"].resolve_public_references(references)


def _error(code):
    return {"error": {"code": code}, "ok": False}
