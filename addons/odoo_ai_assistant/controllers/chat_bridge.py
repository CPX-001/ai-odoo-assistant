"""Odoo-authenticated browser routes for history and user preferences."""

import logging

from odoo import http
from odoo.exceptions import AccessError, ValidationError
from odoo.http import request

from ..models.chat_preferences import recent_chat_limit
from ..services.runtime_account import RuntimeAccountGateError, require_runtime_authenticated

_logger = logging.getLogger(__name__)


class BrowserChatController(http.Controller):
    @http.route(
        "/odoo_ai/v1/chat-history",
        type="json",
        auth="user",
        methods=["POST"],
    )
    def history(self, conversation_id=None, **unexpected):
        if unexpected:
            return _error("invalid_context")
        if not request.env.user._is_internal():
            return _error("access_denied")
        try:
            require_runtime_authenticated(request.env)
            payload = request.env["odoo.ai.conversation"].history_payload(
                conversation_uuid=conversation_id or None,
                max_conversations=recent_chat_limit(request.env),
                max_messages=40,
            )
        except RuntimeAccountGateError as error:
            return _error(error.code)
        except (AccessError, ValidationError, ValueError, TypeError):
            return _error("invalid_context")
        except Exception:  # noqa: BLE001 - browser boundary stays sanitized
            _logger.exception("Odoo-native Assistant history failed")
            return _error("chat_store_unavailable")
        return {"ok": True, **payload}

    @http.route(
        "/odoo_ai/v1/chat-models",
        type="json",
        auth="user",
        methods=["POST"],
    )
    def models(self, **unexpected):
        if unexpected:
            return _error("invalid_context")
        return request.env["odoo.ai.user.preference"].chat_model_preferences()

    @http.route(
        "/odoo_ai/v1/chat-model",
        type="json",
        auth="user",
        methods=["POST"],
    )
    def set_model(self, model=None, **unexpected):
        if unexpected:
            return _error("invalid_context")
        return request.env["odoo.ai.user.preference"].set_chat_model_preference(model)

    @http.route(
        "/odoo_ai/v1/chat-reasoning-effort",
        type="json",
        auth="user",
        methods=["POST"],
    )
    def set_reasoning_effort(self, effort=None, **unexpected):
        if unexpected:
            return _error("invalid_context")
        return request.env[
            "odoo.ai.user.preference"
        ].set_chat_reasoning_effort_preference(effort)

    @http.route(
        "/odoo_ai/v1/planning-mode",
        type="json",
        auth="user",
        methods=["POST"],
    )
    def planning_mode(self, **unexpected):
        if unexpected:
            return _error("invalid_context")
        return request.env["odoo.ai.user.preference"].planning_mode_preferences()

    @http.route(
        "/odoo_ai/v1/planning-mode-set",
        type="json",
        auth="user",
        methods=["POST"],
    )
    def set_planning_mode(self, mode=None, **unexpected):
        if unexpected:
            return _error("invalid_context")
        return request.env["odoo.ai.user.preference"].set_planning_mode_preference(mode)

    @http.route(
        "/odoo_ai/v1/agent-autonomy",
        type="json",
        auth="user",
        methods=["POST"],
    )
    def agent_autonomy(self, **unexpected):
        if unexpected:
            return _error("invalid_context")
        return request.env["odoo.ai.user.preference"].agent_autonomy_preferences()

    @http.route(
        "/odoo_ai/v1/agent-autonomy-set",
        type="json",
        auth="user",
        methods=["POST"],
    )
    def set_agent_autonomy(self, profile=None, **unexpected):
        if unexpected:
            return _error("invalid_context")
        return request.env["odoo.ai.user.preference"].set_agent_autonomy_preference(profile)

    # Compatibility policy endpoints for cached pre-profile frontend assets. They are
    # Odoo-native preferences and do not cross the retired Assistant agent runtime.
    @http.route(
        "/odoo_ai/v1/agent-policy",
        type="json",
        auth="user",
        methods=["POST"],
    )
    def agent_policy(self, **unexpected):
        if unexpected:
            return _error("invalid_context")
        return request.env["odoo.ai.user.preference"].agent_policy_preferences()

    @http.route(
        "/odoo_ai/v1/agent-policy-set",
        type="json",
        auth="user",
        methods=["POST"],
    )
    def set_agent_policy(
        self,
        confirmation_mode=None,
        max_auto_risk=None,
        **unexpected,
    ):
        if unexpected:
            return _error("invalid_context")
        return request.env["odoo.ai.user.preference"].set_agent_policy_preferences(
            confirmation_mode,
            max_auto_risk,
        )


def _error(code):
    return {"error": {"code": code}, "ok": False}
