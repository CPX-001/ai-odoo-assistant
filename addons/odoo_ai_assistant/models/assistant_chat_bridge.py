"""Automatic product chat facade over the existing narrow workflow boundaries."""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping
from time import monotonic
from uuid import UUID

from odoo import api, models

from ..services import (
    AssistantServiceError,
    TurnContextError,
    prepare_agent_turn,
)
from ..services.assistant_chat_client import AssistantChatServiceClient
from .assistant_bridge import (
    DEFAULT_TURN_TIMEOUT_SECONDS,
    SECRET_FILE_ENV,
    SECRET_FILE_PARAM,
    SERVICE_URL_ENV,
    SERVICE_URL_PARAM,
    TURN_TIMEOUT_ENV,
    TURN_TIMEOUT_PARAM,
    _client_error_code,
    _error,
    _turn_timeout,
)
from .chat_preferences import recent_chat_limit

RECOVERABLE_BATCH_ERROR = "batch_execution_outcome_unknown"
_logger = logging.getLogger(__name__)


class AssistantChatBridge(models.AbstractModel):
    _inherit = "odoo.ai.assistant.bridge"

    @api.model
    def submit_turn(self, message, screen, workflow=None):
        """Ignore browser workflow selection and infer the narrow boundary server-side."""

        del workflow
        return self.submit_chat(message, screen)

    @api.model
    def submit_chat(self, message, screen, conversation_id=None):
        if not self.env.user._is_internal():
            return _error("access_denied")
        if not isinstance(screen, Mapping):
            return _error("invalid_context")
        try:
            normalized_message = _chat_message(message)
            conversation_id = _optional_uuid(conversation_id)
            prepare_started = monotonic()
            try:
                prepared = prepare_agent_turn(
                    env=self.env,
                    screen_payload=screen,
                    message=normalized_message,
                )
                payload = prepared.to_assistant_payload()
                policy = self._agent_policy_layers(
                    conversation_id,
                    normalized_message,
                )
                payload.update(
                    {
                        "actor": self._chat_actor(),
                        "conversation_id": conversation_id,
                        "policy_layers": policy["layers"],
                        "synthetic_data_authorized": policy[
                            "synthetic_data_authorized"
                        ],
                    }
                )
            finally:
                _logger.info(
                    "odoo_ai_timing phase=odoo_prepare duration_ms=%d",
                    max(0, round((monotonic() - prepare_started) * 1000)),
                )
            response = _browser_agent(
                self._chat_client().agent_turn(payload),
                prepared.turn_id,
            )

            return self._persist_chat_result(
                response,
                message=normalized_message,
                conversation_id=conversation_id,
                internal_workflow="AGENT",
            )
        except ValueError as error:
            _logger.info("Browser chat rejected invalid value: %s", error)
            return _error("invalid_context")
        except TurnContextError as error:
            _logger.info("Browser chat rejected invalid turn context: %s", error)
            return _error("invalid_context")
        except AssistantServiceError as error:
            return _error(_client_error_code(error.code))
        except Exception:  # noqa: BLE001 - browser boundary stays sanitized
            return _error("service_unavailable")

    @api.model
    def chat_history(self, conversation_id=None):
        if not self.env.user._is_internal():
            return _error("access_denied")
        try:
            parsed_id = _optional_uuid(conversation_id)
            payload = self._chat_client().chat_history(
                {
                    "actor": self._chat_actor(),
                    "conversation_id": parsed_id,
                    "max_conversations": recent_chat_limit(self.env),
                    "max_messages": 40,
                }
            )
            return _browser_history(payload)
        except ValueError:
            return _error("invalid_context")
        except AssistantServiceError as error:
            if error.code in {"conversation_not_found", "diagnostic_not_found"}:
                return _error("invalid_context")
            return _error(_client_error_code(error.code))
        except Exception:  # noqa: BLE001
            return _error("service_unavailable")

    @api.model
    def decide_agent_plan(self, plan_id, decision):
        if not self.env.user._is_internal():
            return _error("access_denied")
        try:
            parsed_plan_id = _required_uuid(plan_id)
            if decision not in {"approve", "reject"}:
                raise ValueError
            actor = self._chat_actor()
            decided = self._chat_client().agent_plan_decision(
                parsed_plan_id,
                {
                    "actor": actor,
                    "decision": decision,
                    "plan_id": parsed_plan_id,
                },
            )
            if decision == "reject":
                return _browser_plan_decision(decided, parsed_plan_id)
            executed = self._chat_client().agent_plan_execute(
                parsed_plan_id,
                {"actor": actor, "plan_id": parsed_plan_id},
            )
            return _browser_plan_execution(executed, parsed_plan_id)
        except ValueError:
            return _error("invalid_context")
        except AssistantServiceError as error:
            return _error(_client_error_code(error.code))
        except Exception:  # noqa: BLE001 - browser boundary stays sanitized
            return _error("service_unavailable")

    @api.model
    def execute_agent_plan(self, plan_id):
        """Resume an already-authorized plan without issuing a second approval."""

        if not self.env.user._is_internal():
            return _error("access_denied")
        try:
            parsed_plan_id = _required_uuid(plan_id)
            actor = self._chat_actor()
            executed = self._chat_client().agent_plan_execute(
                parsed_plan_id,
                {"actor": actor, "plan_id": parsed_plan_id},
            )
            return _browser_plan_execution(executed, parsed_plan_id)
        except ValueError:
            return _error("invalid_context")
        except AssistantServiceError as error:
            return _error(_client_error_code(error.code))
        except Exception:  # noqa: BLE001 - browser boundary stays sanitized
            return _error("service_unavailable")

    @api.model
    def agent_plan_status(self, plan_id):
        """Revalidate a cached plan id against the current Odoo actor."""

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
            return _browser_plan_execution(status, parsed_plan_id)
        except ValueError:
            return _error("invalid_context")
        except AssistantServiceError as error:
            if error.code in {"conversation_not_found", "diagnostic_not_found"}:
                return _error("invalid_context")
            return _error(_client_error_code(error.code))
        except Exception:  # noqa: BLE001 - browser boundary stays sanitized
            return _error("service_unavailable")

    def _agent_policy_layers(self, conversation_id, message):
        return self.env["odoo.ai.chat.policy"].policy_layers_for_turn(
            conversation_id=conversation_id,
            message=message,
        )

    def _persist_chat_result(
        self,
        response,
        *,
        message,
        conversation_id,
        internal_workflow,
    ):
        if not isinstance(response, dict) or response.get("ok") is not True:
            return response
        answer = response.get("answer")
        if not isinstance(answer, str) or not answer:
            return response
        result = dict(response)
        try:
            stored = self._chat_client().chat_append(
                {
                    "actor": self._chat_actor(),
                    "conversation_id": conversation_id,
                    "user_message": message,
                    "assistant_message": answer,
                    "internal_workflow": internal_workflow,
                }
            )
            stored_id = stored.get("conversation_id")
            result["conversation_id"] = (
                stored_id if isinstance(stored_id, str) and _is_uuid(stored_id) else None
            )
        except AssistantServiceError:
            # A transient history failure must not discard an otherwise valid answer.
            result["conversation_id"] = conversation_id
        return result

    def _chat_actor(self):
        return {"database": self.env.cr.dbname, "uid": self.env.uid}

    @api.model
    def _chat_client(self):
        parameters = self.env["ir.config_parameter"]
        service_url = parameters._get_param(SERVICE_URL_PARAM) or os.environ.get(
            SERVICE_URL_ENV
        )
        secret_file = parameters._get_param(SECRET_FILE_PARAM) or os.environ.get(
            SECRET_FILE_ENV
        )
        timeout = _turn_timeout(
            parameters._get_param(TURN_TIMEOUT_PARAM)
            or os.environ.get(TURN_TIMEOUT_ENV)
        )
        if timeout is None:
            timeout = DEFAULT_TURN_TIMEOUT_SECONDS
        if not service_url:
            raise AssistantServiceError("configuration_missing")
        return AssistantChatServiceClient(
            base_url=service_url,
            shared_secret_file=secret_file,
            timeout=timeout,
        )


def _browser_agent(response, turn_id):
    expected = {
        "answer_markdown",
        "completed_at",
        "confidence",
        "conversation_id",
        "plan",
        "state",
        "status",
        "turn_id",
    }
    if not isinstance(response, dict) or set(response) != expected:
        raise AssistantServiceError("invalid_response")
    answer = response.get("answer_markdown")
    plan = _validated_plan(response.get("plan"))
    if (
        response.get("status") != "ok"
        or response.get("turn_id") != str(turn_id)
        or response.get("state") != plan["state"]
        or response.get("confidence") not in {"high", "medium", "low"}
        or not isinstance(answer, str)
        or not 1 <= len(answer) <= 16_384
        or not isinstance(response.get("completed_at"), str)
    ):
        raise AssistantServiceError("invalid_response")
    return {
        "ok": True,
        "turn_id": str(turn_id),
        "workflow": "AGENT",
        "answer": answer,
        "confidence": response["confidence"],
        "limitations": list(plan["assumptions"]),
        "citations": [],
        "plan": plan,
    }


def _validated_plan(value):
    expected = {
        "assumptions",
        "expires_at",
        "goal",
        "metadata",
        "plan_id",
        "policy",
        "requires_confirmation",
        "risk",
        "state",
        "steps",
    }
    states = {
        "planning",
        "awaiting_confirmation",
        "authorized",
        "executing",
        "completed",
        "partial",
        "failed",
        "rejected",
        "expired",
    }
    metadata_keys = {
        "estimated_blast_radius",
        "has_external_effect",
        "has_irreversible_effect",
        "is_atomic",
        "needs_business_action",
        "needs_read",
        "needs_schema",
        "needs_write",
    }
    if (
        not isinstance(value, dict)
        or set(value) != expected
        or not _is_uuid(value.get("plan_id"))
        or value.get("state") not in states
        or value.get("risk") not in {"low", "moderate", "high", "protected"}
        or not isinstance(value.get("goal"), str)
        or not 1 <= len(value["goal"]) <= 1_000
        or not isinstance(value.get("assumptions"), list)
        or len(value["assumptions"]) > 12
        or any(not isinstance(item, str) for item in value["assumptions"])
        or not isinstance(value.get("steps"), list)
        or len(value["steps"]) > 12
        or any(not _valid_plan_step(item) for item in value["steps"])
        or not isinstance(value.get("requires_confirmation"), bool)
        or value.get("expires_at") is not None
        and not isinstance(value.get("expires_at"), str)
        or not isinstance(value.get("metadata"), dict)
        or set(value["metadata"]) != metadata_keys
        or type(value["metadata"].get("estimated_blast_radius")) is not int
        or any(
            not isinstance(value["metadata"].get(key), bool)
            for key in metadata_keys - {"estimated_blast_radius"}
        )
        or not _valid_plan_policy(value.get("policy"))
    ):
        raise AssistantServiceError("invalid_response")
    return dict(value)


def _valid_plan_policy(value):
    return (
        isinstance(value, dict)
        and set(value)
        == {
            "allow_synthetic_data",
            "confirmation_mode",
            "constrained_by",
            "max_auto_risk",
        }
        and value.get("confirmation_mode")
        in {"always_confirm", "risk_based", "protected_only"}
        and value.get("max_auto_risk") in {"low", "moderate", "high", "protected"}
        and isinstance(value.get("allow_synthetic_data"), bool)
        and isinstance(value.get("constrained_by"), list)
        and len(value["constrained_by"]) <= 4
        and all(
            item in {"system_ceiling", "administrator", "user", "conversation"}
            for item in value["constrained_by"]
        )
    )


def _valid_plan_step(value):
    if (
        not isinstance(value, dict)
        or set(value)
        != {"effect_scope", "receipt", "risk", "state", "step_id", "title"}
        or not isinstance(value.get("step_id"), str)
        or not isinstance(value.get("title"), str)
        or not value["title"]
        or value.get("state")
        not in {
            "planned",
            "previewed",
            "executing",
            "completed",
            "partial",
            "failed",
            "skipped",
        }
        or value.get("risk") not in {"low", "moderate", "high", "protected"}
        or value.get("effect_scope")
        not in {"read_only", "internal_reversible", "internal_irreversible", "external"}
    ):
        return False
    receipt = value.get("receipt")
    if receipt is None:
        return True
    return (
        isinstance(receipt, dict)
        and set(receipt)
        == {"error_code", "evidence_id", "outcome", "record_id", "record_model"}
        and isinstance(receipt.get("outcome"), str)
        and (receipt.get("error_code") is None or isinstance(receipt["error_code"], str))
        and (receipt.get("evidence_id") is None or _is_uuid(receipt["evidence_id"]))
        and (
            receipt.get("record_id") is None
            and receipt.get("record_model") is None
            or type(receipt.get("record_id")) is int
            and receipt["record_id"] > 0
            and isinstance(receipt.get("record_model"), str)
        )
    )


def _browser_plan_decision(response, plan_id):
    if (
        not isinstance(response, dict)
        or set(response) != {"authorization_id", "decided_at", "plan_id", "state"}
        or response.get("plan_id") != plan_id
        or response.get("state") != "rejected"
        or response.get("authorization_id") is not None
        or not isinstance(response.get("decided_at"), str)
    ):
        raise AssistantServiceError("invalid_response")
    return {"ok": True, "plan_id": plan_id, "state": "rejected", "plan": None}


def _browser_plan_execution(response, plan_id):
    if (
        not isinstance(response, dict)
        or set(response) != {"answer_markdown", "completed_at", "error_code", "plan"}
    ):
        raise AssistantServiceError("invalid_response")
    plan = _validated_plan(response.get("plan"))
    state = plan.get("state")
    if (
        plan.get("plan_id") != plan_id
        or state not in {"authorized", "completed", "partial", "failed"}
        or response.get("completed_at") is not None
        and not isinstance(response.get("completed_at"), str)
        or response.get("error_code") is not None
        and not isinstance(response.get("error_code"), str)
        or state == "authorized"
        and (
            response.get("error_code") != RECOVERABLE_BATCH_ERROR
            or response.get("completed_at") is not None
        )
    ):
        raise AssistantServiceError("invalid_response")
    return {"ok": True, "plan_id": plan_id, "state": state, "plan": plan}


def _browser_history(payload):
    if not isinstance(payload, dict) or set(payload) != {
        "active_conversation_id",
        "conversations",
        "messages",
    }:
        raise AssistantServiceError("invalid_response")
    conversations = payload.get("conversations")
    messages = payload.get("messages")
    active = payload.get("active_conversation_id")
    if (
        not isinstance(conversations, list)
        or len(conversations) > 50
        or not isinstance(messages, list)
        or len(messages) > 80
        or active is not None
        and not _is_uuid(active)
    ):
        raise AssistantServiceError("invalid_response")
    clean_conversations = []
    for item in conversations:
        if (
            not isinstance(item, dict)
            or set(item) != {"conversation_id", "created_at", "title", "updated_at"}
            or not _is_uuid(item.get("conversation_id"))
            or not isinstance(item.get("title"), str)
            or not 1 <= len(item["title"]) <= 160
            or not isinstance(item.get("created_at"), str)
            or not isinstance(item.get("updated_at"), str)
        ):
            raise AssistantServiceError("invalid_response")
        clean_conversations.append(dict(item))
    clean_messages = []
    for item in messages:
        if (
            not isinstance(item, dict)
            or set(item) != {"content", "created_at", "message_id", "role"}
            or not _is_uuid(item.get("message_id"))
            or item.get("role") not in {"user", "assistant"}
            or not isinstance(item.get("content"), str)
            or not 1 <= len(item["content"]) <= 16_384
            or not isinstance(item.get("created_at"), str)
        ):
            raise AssistantServiceError("invalid_response")
        clean_messages.append(dict(item))
    return {
        "ok": True,
        "active_conversation_id": active,
        "conversations": clean_conversations,
        "messages": clean_messages,
    }


def _chat_message(value) -> str:
    if not isinstance(value, str):
        raise TypeError
    normalized = value.strip()
    if not 1 <= len(normalized) <= 4_000 or "\x00" in normalized:
        raise ValueError
    return normalized


def _optional_uuid(value):
    if value in (None, ""):
        return None
    if not isinstance(value, str) or not _is_uuid(value):
        raise ValueError
    return value


def _required_uuid(value):
    parsed = _optional_uuid(value)
    if parsed is None:
        raise ValueError
    return parsed


def _is_uuid(value) -> bool:
    if not isinstance(value, str):
        return False
    try:
        return str(UUID(value)) == value
    except ValueError:
        return False
