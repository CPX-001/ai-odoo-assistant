"""Odoo-authenticated browser routes for native chat history actions."""

import logging

from odoo import http
from odoo.exceptions import AccessError, ValidationError
from odoo.http import request

_logger = logging.getLogger(__name__)


class BrowserChatHistoryActionsController(http.Controller):
    @http.route(
        "/odoo_ai/v1/chat-delete",
        type="json",
        auth="user",
        methods=["POST"],
    )
    def delete(self, conversation_ids=None, **unexpected):
        if unexpected or not isinstance(conversation_ids, list):
            return _error("invalid_context")
        if not request.env.user._is_internal():
            return _error("access_denied")
        try:
            deleted = request.env["odoo.ai.conversation"].delete_owned(conversation_ids)
        except (AccessError, ValidationError, ValueError, TypeError):
            return _error("invalid_context")
        except Exception:  # noqa: BLE001 - browser boundary stays sanitized
            _logger.exception("Odoo-native Assistant history deletion failed")
            return _error("chat_store_unavailable")
        return {"ok": True, "deleted_count": deleted}


def _error(code):
    return {"error": {"code": code}, "ok": False}
