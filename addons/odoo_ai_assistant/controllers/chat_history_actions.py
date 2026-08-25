"""Odoo-authenticated browser routes for chat history actions."""

from odoo import http
from odoo.http import request


class BrowserChatHistoryActionsController(http.Controller):
    @http.route(
        "/odoo_ai/v1/chat-delete",
        type="json",
        auth="user",
        methods=["POST"],
    )
    def delete(self, conversation_ids=None, **unexpected):
        if unexpected:
            return {"error": {"code": "invalid_context"}, "ok": False}
        return request.env["odoo.ai.assistant.bridge"].delete_chat_conversations(
            conversation_ids
        )
