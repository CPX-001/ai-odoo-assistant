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

    @http.route(
        "/odoo_ai/v1/chat-models",
        type="json",
        auth="user",
        methods=["POST"],
    )
    def models(self, **unexpected):
        if unexpected:
            return {"error": {"code": "invalid_context"}, "ok": False}
        return request.env["odoo.ai.assistant.bridge"].chat_model_preferences()

    @http.route(
        "/odoo_ai/v1/chat-model",
        type="json",
        auth="user",
        methods=["POST"],
    )
    def set_model(self, model=None, **unexpected):
        if unexpected:
            return {"error": {"code": "invalid_context"}, "ok": False}
        return request.env["odoo.ai.assistant.bridge"].set_chat_model_preference(model)

    @http.route(
        "/odoo_ai/v1/agent-plan-decision",
        type="json",
        auth="user",
        methods=["POST"],
    )
    def agent_plan_decision(self, plan_id=None, decision=None, **unexpected):
        if unexpected:
            return {"error": {"code": "invalid_context"}, "ok": False}
        return request.env["odoo.ai.assistant.bridge"].decide_agent_plan(
            plan_id,
            decision,
        )

    @http.route(
        "/odoo_ai/v1/agent-policy",
        type="json",
        auth="user",
        methods=["POST"],
    )
    def agent_policy(self, **unexpected):
        if unexpected:
            return {"error": {"code": "invalid_context"}, "ok": False}
        return request.env["odoo.ai.assistant.bridge"].agent_policy_preferences()

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
            return {"error": {"code": "invalid_context"}, "ok": False}
        return request.env["odoo.ai.assistant.bridge"].set_agent_policy_preferences(
            confirmation_mode,
            max_auto_risk,
        )
