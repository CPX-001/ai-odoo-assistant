"""Automatic product chat facade over the existing narrow workflow boundaries."""

from __future__ import annotations

import os
import re
import unicodedata
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

_ACTION_WORDS = re.compile(
    r"\b(cambia|cambiar|actualiza|actualizar|modifica|modificar|pon|establece|crea|crear|"
    r"confirma|confirmar|cancela|cancelar|elimina|eliminar|borra|borrar|change|update|set|"
    r"create|confirm|cancel|delete|remove)\b",
    re.IGNORECASE,
)
_HOW_TO = re.compile(
    r"(^|\b)(como|cómo|como puedo|cómo puedo|donde|dónde|pasos para|how do|how can|where do)\b",
    re.IGNORECASE,
)
_QUERY = re.compile(
    r"\b(cuantos|cuántos|cuantas|cuántas|lista|listame|lístame|muestra|muéstrame|dime|busca|"
    r"encuentra|total|suma|promedio|count|list|show|find|search|total|sum|average)\b",
    re.IGNORECASE,
)
_SELECTOR_QUESTION = re.compile(
    r"^\s*[¿?]?(que|qué|cual|cuál|cuales|cuáles|which|what)\b",
    re.IGNORECASE,
)
_EXPLAIN = re.compile(
    r"\b(por que|por qué|explica|explicame|explícame|que significa|qué significa|que es esto|"
    r"qué es esto|why|explain|what does)\b",
    re.IGNORECASE,
)
_MODEL_NAME = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z0-9_.]+\b")


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
            query_screen, query_score = self._query_screen(
                normalized_message,
                validated.to_mapping(),
            )

            if _HOW_TO.search(normalized_message):
                internal_workflow = "HOW_TO"
                response = self.submit_how_to(normalized_message, screen)
            elif (
                _ACTION_WORDS.search(normalized_message)
                and validated.model is not None
                and validated.res_id is not None
                and (query_score == 0 or query_screen.get("model") == validated.model)
            ):
                internal_workflow = "ACTION"
                response = self.submit_action(normalized_message, screen)
            elif query_screen.get("model") is not None and (
                _QUERY.search(normalized_message)
                or (_SELECTOR_QUESTION.search(normalized_message) and query_score > 0)
            ):
                internal_workflow = "QUERY"
                response = self.submit_query(normalized_message, query_screen)
            elif (
                _EXPLAIN.search(normalized_message)
                and validated.model is not None
                and validated.res_id is not None
            ):
                internal_workflow = "EXPLAIN"
                response = self.submit_explain(normalized_message, screen)
            else:
                internal_workflow = "GENERAL"
                response = self._submit_general(
                    normalized_message,
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

    def _query_screen(self, message: str, screen: dict[str, object]):
        current_model = screen.get("model") if isinstance(screen.get("model"), str) else None
        target, score = _infer_target_model(self.env, message, current_model)
        if target is None:
            return screen, 0
        if target == current_model:
            return screen, score
        return {
            "action_id": None,
            "allowed_context_subset": {},
            "captured_at": screen["captured_at"],
            "menu_id": None,
            "model": target,
            "res_id": None,
            "selected_ids": [],
            "view_type": None,
        }, score

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


def _infer_target_model(env, message: str, current_model: str | None):
    for candidate in _MODEL_NAME.findall(message):
        if _readable_model(env, candidate):
            return candidate, 100

    message_tokens = _tokens(message)
    best_model = None
    best_score = 0
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
                label_tokens = _tokens(" ".join(value for value in path if isinstance(value, str)))
                model_tokens = set(target.replace(".", " ").replace("_", " ").split())
                score = 4 * len(message_tokens & label_tokens) + len(message_tokens & model_tokens)
                if score > best_score:
                    best_model = target
                    best_score = score
    except NavigationMetadataError:
        pass

    if best_model is not None:
        return best_model, best_score
    if current_model is not None and _readable_model(env, current_model):
        return current_model, 0
    return None, 0


def _readable_model(env, model: str) -> bool:
    try:
        if model not in env:
            return False
        env[model].browse().check_access("read")
        return True
    except (AccessError, MissingError, KeyError, ValueError):
        return False


def _tokens(value: str) -> set[str]:
    folded = unicodedata.normalize("NFKD", value.casefold())
    ascii_value = "".join(char for char in folded if not unicodedata.combining(char))
    return {
        token
        for token in re.findall(r"[a-z0-9_]{3,}", ascii_value)
        if token not in {"para", "como", "esta", "este", "esto", "with", "from", "that"}
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
