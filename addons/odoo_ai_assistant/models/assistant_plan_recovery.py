"""Browser-safe status extension for durable agent-plan recovery."""

from odoo import api, models

from ..services import AssistantServiceError
from .assistant_bridge import _client_error_code, _error
from .assistant_chat_bridge import (
    RECOVERABLE_BATCH_ERROR,
    _required_uuid,
    _validated_plan,
)


class AssistantPlanRecoveryBridge(models.AbstractModel):
    _inherit = "odoo.ai.assistant.bridge"

    @api.model
    def agent_plan_status(self, plan_id):
        """Revalidate a cached plan id without treating EXECUTING as corruption."""

        if not self.env.user._is_internal():
            return _error("access_denied")
        try:
            parsed_plan_id = _required_uuid(plan_id)
            actor = self._chat_actor()
            status = self._chat_client().agent_plan_status(
                parsed_plan_id,
                database=actor["database"],
                uid=actor["uid"],
            )
            return _browser_plan_status(status, parsed_plan_id)
        except ValueError:
            return _error("invalid_context")
        except AssistantServiceError as error:
            if error.code in {"conversation_not_found", "diagnostic_not_found"}:
                return _error("invalid_context")
            return _error(_client_error_code(error.code))
        except Exception:  # noqa: BLE001 - browser boundary stays sanitized
            return _error("service_unavailable")


def _browser_plan_status(response, plan_id):
    expected = {"answer_markdown", "completed_at", "error_code", "plan"}
    if not isinstance(response, dict) or set(response) != expected:
        raise AssistantServiceError("invalid_response")
    plan = _validated_plan(response.get("plan"))
    state = plan.get("state")
    if (
        plan.get("plan_id") != plan_id
        or state
        not in {
            "authorized",
            "executing",
            "completed",
            "partial",
            "failed",
            "rejected",
            "expired",
        }
        or response.get("completed_at") is not None
        and not isinstance(response.get("completed_at"), str)
        or response.get("error_code") is not None
        and not isinstance(response.get("error_code"), str)
    ):
        raise AssistantServiceError("invalid_response")
    if state == "authorized" and (
        response.get("error_code") != RECOVERABLE_BATCH_ERROR
        or response.get("completed_at") is not None
    ):
        raise AssistantServiceError("invalid_response")
    if state == "executing" and (
        response.get("error_code") is not None
        or response.get("completed_at") is not None
    ):
        raise AssistantServiceError("invalid_response")
    return {"ok": True, "plan_id": plan_id, "state": state, "plan": plan}
