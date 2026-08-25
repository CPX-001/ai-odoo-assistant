"""Odoo-authenticated browser routes for the product-facing chat facade."""

import json
import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)
_MAX_STREAM_SCREEN_CHARS = 16 * 1024


class BrowserChatController(http.Controller):
    @http.route(
        "/odoo_ai/v1/chat",
        type="json",
        auth="user",
        methods=["POST"],
    )
    def chat(self, message=None, screen=None, conversation_id=None, **unexpected):
        if unexpected:
            _logger.info(
                "Browser chat rejected unexpected payload keys: %s",
                sorted(unexpected),
            )
            return {"error": {"code": "invalid_context"}, "ok": False}
        return request.env["odoo.ai.assistant.bridge"].submit_chat(
            message,
            screen,
            conversation_id,
        )

    @http.route(
        "/odoo_ai/v1/chat/stream",
        type="http",
        auth="user",
        methods=["POST"],
    )
    def chat_stream(self, message=None, screen=None, conversation_id=None, **unexpected):
        """Relay Assistant SSE while keeping browser auth/authority entirely in Odoo."""

        bridge = request.env["odoo.ai.assistant.bridge"]
        if unexpected:
            _logger.info(
                "Browser streaming chat rejected unexpected payload keys: %s",
                sorted(unexpected),
            )
            return _single_failure_stream(
                bridge,
                "invalid_context",
                message,
                conversation_id,
            )
        try:
            if not isinstance(screen, str) or not 1 <= len(screen) <= _MAX_STREAM_SCREEN_CHARS:
                raise ValueError
            screen_payload = json.loads(screen)
            if not isinstance(screen_payload, dict):
                raise ValueError
        except (TypeError, ValueError):
            return _single_failure_stream(
                bridge,
                "invalid_context",
                message,
                conversation_id,
            )

        try:
            prepared = bridge.prepare_chat_stream(
                message,
                screen_payload,
                conversation_id,
            )
        except Exception as error:  # noqa: BLE001 - browser response stays sanitized
            code = getattr(error, "code", "service_unavailable")
            if not isinstance(code, str) or not code:
                code = "service_unavailable"
            _logger.info("Browser streaming chat preparation failed: %s", code)
            return _single_failure_stream(
                bridge,
                code,
                message,
                conversation_id,
            )
        return _stream_response(prepared.iter_sse())

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
        "/odoo_ai/v1/agent-autonomy",
        type="json",
        auth="user",
        methods=["POST"],
    )
    def agent_autonomy(self, **unexpected):
        if unexpected:
            return {"error": {"code": "invalid_context"}, "ok": False}
        return request.env["odoo.ai.assistant.bridge"].agent_autonomy_preferences()

    @http.route(
        "/odoo_ai/v1/agent-autonomy-set",
        type="json",
        auth="user",
        methods=["POST"],
    )
    def set_agent_autonomy(self, profile=None, **unexpected):
        if unexpected:
            return {"error": {"code": "invalid_context"}, "ok": False}
        return request.env["odoo.ai.assistant.bridge"].set_agent_autonomy_preference(
            profile
        )

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
        "/odoo_ai/v1/agent-plan-execute",
        type="json",
        auth="user",
        methods=["POST"],
    )
    def agent_plan_execute(self, plan_id=None, **unexpected):
        if unexpected:
            return {"error": {"code": "invalid_context"}, "ok": False}
        return request.env["odoo.ai.assistant.bridge"].execute_agent_plan(plan_id)

    @http.route(
        "/odoo_ai/v1/agent-plan-status",
        type="json",
        auth="user",
        methods=["POST"],
    )
    def agent_plan_status(self, plan_id=None, **unexpected):
        if unexpected:
            return {"error": {"code": "invalid_context"}, "ok": False}
        return request.env["odoo.ai.assistant.bridge"].agent_plan_status(plan_id)

    # Legacy policy endpoints remain available for older cached assets during module
    # upgrades. New clients use the single autonomy-profile endpoints above.
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


def _single_failure_stream(bridge, code, message, conversation_id):
    try:
        result = bridge.chat_stream_preparation_failure(
            code,
            message,
            conversation_id,
        )
    except Exception:  # noqa: BLE001 - never expose a controller exception to chat
        result = _emergency_failure_result()
    return _stream_response(
        iter(
            (
                _sse_event(
                    "final",
                    {"type": "final", "response": result},
                ),
            )
        )
    )


def _emergency_failure_result():
    """Return a final envelope that remains valid even if every richer fallback failed."""

    return {
        "ok": True,
        "turn_id": "00000000-0000-4000-8000-000000000001",
        "workflow": "AGENT",
        "answer": (
            "No he podido completar la petición de forma fiable. No tengo suficiente "
            "información para afirmar la causa y no voy a inventarla. Si pedías modificar "
            "datos, comprueba su estado actual antes de repetir la operación."
        ),
        "confidence": "low",
        "limitations": [],
        "citations": [],
        "plan": {
            "plan_id": "00000000-0000-4000-8000-000000000002",
            "state": "failed",
            "risk": "low",
            "metadata": {
                "needs_read": False,
                "needs_schema": False,
                "needs_write": False,
                "needs_business_action": False,
                "has_external_effect": False,
                "has_irreversible_effect": False,
                "is_atomic": True,
                "estimated_blast_radius": 0,
            },
            "policy": {
                "confirmation_mode": "risk_based",
                "max_auto_risk": "low",
                "allow_synthetic_data": False,
                "constrained_by": [],
            },
            "goal": "Explicar que no se pudo completar la petición.",
            "assumptions": [],
            "steps": [],
            "requires_confirmation": False,
            "expires_at": None,
        },
        "conversation_id": None,
    }


def _stream_response(iterator):
    return http.Response(
        iterator,
        status=200,
        content_type="text/event-stream; charset=utf-8",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
        direct_passthrough=True,
    )


def _sse_event(event, payload):
    encoded = json.dumps(
        payload,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return f"event: {event}\ndata: {encoded}\n\n".encode("utf-8")
