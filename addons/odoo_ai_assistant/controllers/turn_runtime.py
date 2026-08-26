"""Short Odoo-authenticated endpoints for the persistent embedded turn runtime."""

from __future__ import annotations

import logging

from odoo import http
from odoo.exceptions import AccessError, ValidationError
from odoo.http import request

from ..runtime import (
    CodexAccountError,
    CodexAccountManager,
    RuntimePathError,
    RuntimePaths,
    detect_codex,
)

_logger = logging.getLogger(__name__)


class AssistantTurnController(http.Controller):
    @http.route(
        "/odoo_ai/v1/runtime-status",
        type="json",
        auth="user",
        methods=["POST"],
    )
    def runtime_status(self, **unexpected):
        if unexpected:
            return _error("invalid_context")
        can_configure = request.env.user.has_group("base.group_system")
        codex = detect_codex()
        if not codex.ready or codex.executable is None:
            return _runtime_status("codex_unavailable", can_configure)
        try:
            paths = RuntimePaths.from_odoo().ensure()
            account = CodexAccountManager(
                executable=codex.executable,
                paths=paths,
            ).status(include_rate_limits=False)
        except (CodexAccountError, RuntimePathError):
            return _runtime_status("authentication_error", can_configure)
        state = account.state
        if state not in {
            "authenticated",
            "authentication_error",
            "login_pending",
            "not_authenticated",
        }:
            state = "authentication_error"
        return _runtime_status(state, can_configure)

    @http.route("/odoo_ai/v1/turn", type="json", auth="user", methods=["POST"])
    def enqueue_turn(
        self,
        message=None,
        screen=None,
        conversation_id=None,
        client_request_id=None,
        **unexpected,
    ):
        if unexpected:
            return _error("invalid_context")
        try:
            return request.env["odoo.ai.turn"].enqueue_for_current_user(
                message=message,
                screen=screen,
                conversation_uuid=conversation_id or None,
                client_request_id=client_request_id or None,
            )
        except (AccessError, ValidationError):
            return _error("invalid_context")
        except Exception:  # noqa: BLE001
            _logger.exception("Assistant turn enqueue failed")
            return _error("runtime_unavailable")

    @http.route(
        "/odoo_ai/v1/turn/status",
        type="json",
        auth="user",
        methods=["POST"],
    )
    def turn_status(self, turn_id=None, after_sequence=0, **unexpected):
        if unexpected:
            return _error("invalid_context")
        try:
            return request.env["odoo.ai.turn"].status_for_current_user(
                turn_id,
                after_sequence=after_sequence,
            )
        except (AccessError, ValidationError, ValueError, TypeError):
            return _error("turn_not_found")
        except Exception:  # noqa: BLE001
            _logger.exception("Assistant turn status failed")
            return _error("runtime_unavailable")

    @http.route(
        "/odoo_ai/v1/turn/cancel",
        type="json",
        auth="user",
        methods=["POST"],
    )
    def cancel_turn(self, turn_id=None, **unexpected):
        if unexpected:
            return _error("invalid_context")
        try:
            return request.env["odoo.ai.turn"].cancel_for_current_user(turn_id)
        except (AccessError, ValidationError):
            return _error("turn_not_found")
        except Exception:  # noqa: BLE001
            _logger.exception("Assistant turn cancellation failed")
            return _error("runtime_unavailable")

    @http.route(
        "/odoo_ai/v1/turn/plan-decision",
        type="json",
        auth="user",
        methods=["POST"],
    )
    def plan_decision(self, plan_id=None, decision=None, **unexpected):
        if unexpected:
            return _error("invalid_context")
        try:
            return request.env["odoo.ai.turn"].decide_capability_plan_for_current_user(
                plan_id,
                decision,
            )
        except (AccessError, ValidationError, ValueError, TypeError):
            return _error("invalid_context")
        except Exception:  # noqa: BLE001
            _logger.exception("Assistant plan decision failed")
            return _error("runtime_unavailable")

    @http.route(
        "/odoo_ai/v1/turn/plan-status",
        type="json",
        auth="user",
        methods=["POST"],
    )
    def plan_status(self, plan_id=None, **unexpected):
        if unexpected:
            return _error("invalid_context")
        try:
            return request.env["odoo.ai.turn"].capability_plan_status_for_current_user(
                plan_id
            )
        except (AccessError, ValidationError, ValueError, TypeError):
            return _error("invalid_context")
        except Exception:  # noqa: BLE001
            _logger.exception("Assistant plan status failed")
            return _error("runtime_unavailable")


def _error(code):
    return {"ok": False, "error": {"code": code}}


def _runtime_status(state, can_configure):
    return {
        "ok": True,
        "state": state,
        "requires_setup": state != "authenticated",
        "can_configure": bool(can_configure),
    }
