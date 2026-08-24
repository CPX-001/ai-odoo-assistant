"""Odoo-authenticated browser routes for the product-facing chat facade."""

from odoo import http
from odoo.http import request


class BrowserChatController(http.Controller):
    @http.route(
        "/odoo_ai/v1/chat",
        type="json",
        auth="user",
        methods=["POST"],
    )
    def chat(self, message=None, screen=None, conversation_id=None, **unexpected):
        if unexpected:
            return {"error": {"code": "invalid_context"}, "ok": False}
        return request.env["odoo.ai.assistant.bridge"].submit_chat(
            message,
            screen,
            conversation_id,
        )

    @http.route(
        "/odoo_ai/v1/chat-history",
        type="json",
        auth="user",
        methods=["POST"],
    )
    def history(self, conversation_id=None, **unexpected):
        if unexpected:
            return {"error": {"code": "invalid_context"}, "ok": False}
        return request.env["odoo.ai.assistant.bridge"].chat_history(conversation_id)
