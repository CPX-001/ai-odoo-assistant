"""Automatic product chat facade over the existing narrow workflow boundaries."""

from __future__ import annotations

import os
from collections.abc import Mapping
from datetime import UTC, datetime
from uuid import UUID, uuid4

from odoo import api, models
from odoo.exceptions import AccessError, MissingError

from ..services import (
    AssistantServiceError,
    ScreenContextValidationError,
    TurnContextError,
    derive_user_execution_context,
    validate_how_to_screen,
)
from ..services.assistant_chat_client import AssistantChatServiceClient
from ..services.navigation import NavigationMetadataError, collect_visible_navigation
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

_CHAT_WORKFLOWS = frozenset({"GENERAL", "EXPLAIN", "QUERY", "HOW_TO", "ACTION"})
_MAX_ROUTE_MODELS = 128
_MAX_ROUTE_LABELS = 6


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
            validated = validate_how_to_screen(screen)
            route = self._route_chat(
                normalized_message,
                validated.to_mapping(),
                conversation_id,
            )
            internal_workflow = route["workflow"]
            target_model = route["target_model"]
            routed_message = route["resolved_message"]
            routed_screen = _screen_for_model(validated.to_mapping(), target_model)

            if internal_workflow == "HOW_TO":
                response = self.submit_how_to(routed_message, routed_screen)
            elif internal_workflow == "ACTION":
                response = self.submit_action(routed_message, screen)
            elif internal_workflow == "QUERY":
                response = self.submit_query(routed_message, routed_screen)
            elif internal_workflow == "EXPLAIN":
                response = self.submit_explain(routed_message, screen)
            else:
                response = self._submit_general(
                    routed_message,
                    validated.to_mapping(),
                    conversation_id,
                )

            return self._persist_chat_result(
                response,
                message=normalized_message,
                conversation_id=conversation_id,
                internal_workflow=internal_workflow,
            )
        except (ScreenContextValidationError, ValueError):
            return _error("invalid_context")
        except TurnContextError:
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

    def _submit_general(self, message, screen, conversation_id):
        turn_id = uuid4()
        user = derive_user_execution_context(self.env)
        response = self._chat_client().general_chat(
            {
                "turn_id": str(turn_id),
                "actor": self._chat_actor(),
                "conversation_id": conversation_id,
                "message": message,
                "screen": screen,
                "user": user.to_mapping(),
            }
        )
        return _browser_general(response, turn_id)

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

    def _route_chat(self, message, screen, conversation_id):
        candidates = _routing_candidates(self.env, screen.get("model"))
        allowed_models = {candidate["model"] for candidate in candidates}
        current_model = screen.get("model")
        if not isinstance(current_model, str) or current_model not in allowed_models:
            current_model = None
        route_id = uuid4()
        response = self._chat_client().route_chat(
            {
                "actor": self._chat_actor(),
                "candidates": candidates,
                "conversation_id": conversation_id,
                "current_model": current_model,
                "has_current_record": current_model is not None
                and isinstance(screen.get("res_id"), int),
                "message": message,
                "turn_id": str(route_id),
                "user_language": self.env.user.lang or "en_US",
            }
        )
        return _validated_route(
            response,
            route_id=route_id,
            allowed_models=allowed_models,
            current_model=current_model,
            has_current_record=current_model is not None
            and isinstance(screen.get("res_id"), int),
        )

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


def _routing_candidates(env, current_model) -> list[dict[str, object]]:
    labels_by_model: dict[str, list[str]] = {}
    if isinstance(current_model, str) and _readable_model(env, current_model):
        labels_by_model[current_model] = []
    try:
        navigation = collect_visible_navigation(env, captured_at=datetime.now(UTC))
        nodes = navigation.get("nodes")
        if isinstance(nodes, list):
            for node in nodes:
                if not isinstance(node, dict):
                    continue
                action = node.get("action")
                path = node.get("path")
                if not isinstance(action, dict) or not isinstance(path, list):
                    continue
                target = action.get("target_model")
                if not isinstance(target, str) or not _readable_model(env, target):
                    continue
                labels = labels_by_model.setdefault(target, [])
                label = " / ".join(value.strip() for value in path if isinstance(value, str))
                if (
                    1 <= len(label) <= 240
                    and label not in labels
                    and len(labels) < _MAX_ROUTE_LABELS
                ):
                    labels.append(label)
                if len(labels_by_model) >= _MAX_ROUTE_MODELS:
                    break
    except NavigationMetadataError:
        pass
    return [
        {"labels": labels, "model": model}
        for model, labels in list(labels_by_model.items())[:_MAX_ROUTE_MODELS]
    ]


def _readable_model(env, model: str) -> bool:
    try:
        if model not in env:
            return False
        env[model].browse().check_access("read")
        return True
    except (AccessError, MissingError, KeyError, ValueError):
        return False


def _screen_for_model(screen: dict[str, object], target_model) -> dict[str, object]:
    if target_model == screen.get("model"):
        return screen
    return {
        "action_id": None,
        "allowed_context_subset": {},
        "captured_at": screen["captured_at"],
        "menu_id": None,
        "model": target_model,
        "res_id": None,
        "selected_ids": [],
        "view_type": None,
    }


def _validated_route(
    response,
    *,
    route_id,
    allowed_models,
    current_model,
    has_current_record,
):
    expected = {"resolved_message", "status", "target_model", "turn_id", "workflow"}
    if not isinstance(response, dict) or set(response) != expected:
        raise AssistantServiceError("invalid_response")
    workflow = response.get("workflow")
    target_model = response.get("target_model")
    resolved_message = response.get("resolved_message")
    if (
        response.get("status") != "ok"
        or response.get("turn_id") != str(route_id)
        or workflow not in _CHAT_WORKFLOWS
        or (target_model is not None and target_model not in allowed_models)
        or not isinstance(resolved_message, str)
        or not 1 <= len(resolved_message) <= 4_000
        or resolved_message != resolved_message.strip()
        or "\0" in resolved_message
    ):
        raise AssistantServiceError("invalid_response")
    if workflow == "QUERY" and target_model is None:
        raise AssistantServiceError("invalid_response")
    if workflow in {"ACTION", "EXPLAIN"} and (
        not has_current_record
        or target_model is None
        or target_model != current_model
    ):
        raise AssistantServiceError("invalid_response")
    if workflow == "GENERAL" and target_model is not None:
        raise AssistantServiceError("invalid_response")
    return {
        "resolved_message": resolved_message,
        "target_model": target_model,
        "workflow": workflow,
    }


def _browser_general(response, turn_id):
    expected = {
        "answer_markdown",
        "completed_at",
        "confidence",
        "evidence_refs",
        "limitations",
        "status",
        "turn_id",
        "workflow",
    }
    if not isinstance(response, dict) or set(response) != expected:
        raise AssistantServiceError("invalid_response")
    answer = response.get("answer_markdown")
    limitations = response.get("limitations")
    references = response.get("evidence_refs")
    if (
        response.get("status") != "ok"
        or response.get("turn_id") != str(turn_id)
        or response.get("workflow") == "ACTION"
        or response.get("confidence") not in {"high", "medium", "low"}
        or not isinstance(answer, str)
        or not 1 <= len(answer) <= 16_384
        or not isinstance(limitations, list)
        or len(limitations) > 8
        or any(not isinstance(value, str) or not 1 <= len(value) <= 1_024 for value in limitations)
        or not isinstance(references, list)
        or len(references) > 24
        or any(not _is_uuid(value) for value in references)
        or not isinstance(response.get("completed_at"), str)
    ):
        raise AssistantServiceError("invalid_response")
    return {
        "ok": True,
        "turn_id": str(turn_id),
        "workflow": "GENERAL",
        "answer": answer,
        "confidence": response["confidence"],
        "limitations": list(limitations),
        "citations": [],
    }


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
        raise ValueError
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


def _is_uuid(value) -> bool:
    if not isinstance(value, str):
        return False
    try:
        return str(UUID(value)) == value
    except ValueError:
        return False
