"""Authenticated, narrow browser ingress for one contextual read turn."""

from typing import Final

from odoo import http
from odoo.http import request

BROWSER_CONTEXT_READ_ROUTE: Final = "/odoo_ai/v1/context-read"
BROWSER_EXPLAIN_ROUTE: Final = "/odoo_ai/v1/explain"
BROWSER_QUERY_ROUTE: Final = "/odoo_ai/v1/query"
BROWSER_HOW_TO_ROUTE: Final = "/odoo_ai/v1/how-to"
BROWSER_TURN_ROUTE: Final = "/odoo_ai/v1/turn"


class BrowserAssistantController(http.Controller):
    """Accept navigation hints while deriving all authority from the session."""

    @http.route(
        BROWSER_TURN_ROUTE,
        type="json",
        auth="user",
        methods=["POST"],
    )
    def turn(self, message=None, screen=None, workflow=None, **unexpected):
        if unexpected:
            return {"error": {"code": "invalid_context"}, "ok": False}
        return request.env["odoo.ai.assistant.bridge"].submit_turn(
            message, screen, workflow
        )

    @http.route(
        BROWSER_CONTEXT_READ_ROUTE,
        type="json",
        auth="user",
        methods=["POST"],
    )
    def context_read(self, message=None, screen=None, **unexpected):
        if unexpected:
            return {"error": {"code": "invalid_context"}, "ok": False}
        return request.env["odoo.ai.assistant.bridge"].submit_context_read(
            message, screen
        )

    @http.route(
        BROWSER_EXPLAIN_ROUTE,
        type="json",
        auth="user",
        methods=["POST"],
    )
    def explain(self, message=None, screen=None, **unexpected):
        if unexpected:
            return {"error": {"code": "invalid_context"}, "ok": False}
        return request.env["odoo.ai.assistant.bridge"].submit_explain(message, screen)

    @http.route(
        BROWSER_QUERY_ROUTE,
        type="json",
        auth="user",
        methods=["POST"],
    )
    def query(self, message=None, screen=None, **unexpected):
        if unexpected:
            return {"error": {"code": "invalid_context"}, "ok": False}
        return request.env["odoo.ai.assistant.bridge"].submit_query(message, screen)

    @http.route(
        BROWSER_HOW_TO_ROUTE,
        type="json",
        auth="user",
        methods=["POST"],
    )
    def how_to(self, message=None, screen=None, **unexpected):
        if unexpected:
            return {"error": {"code": "invalid_context"}, "ok": False}
        return request.env["odoo.ai.assistant.bridge"].submit_how_to(message, screen)
