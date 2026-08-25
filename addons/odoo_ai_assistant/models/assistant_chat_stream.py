"""Odoo-owned preparation and cursor-free relay for browser chat streaming."""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from uuid import UUID, uuid4

from odoo import api, models

from ..services import AssistantServiceError, TurnContextError, prepare_agent_turn
from ..services.assistant_chat_client import AssistantChatServiceClient
from .assistant_bridge import _client_error_code
from .assistant_chat_bridge import (
    _browser_agent,
    _chat_message,
    _is_uuid,
    _optional_uuid,
)
from .assistant_chat_failures import _failure_answer, _failure_plan

_BROWSER_STREAM_DELTA_MAX_CHARS = 4096


class ChatStreamPreparationError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class PreparedBrowserChatStream:
    """Everything the WSGI iterator needs after Odoo closes the request cursor."""

    client: AssistantChatServiceClient
    payload: dict[str, object]
    turn_id: UUID
    actor: dict[str, object]
    message: str
    conversation_id: str | None
    failure_plan: dict[str, object]

    def iter_sse(self) -> Iterator[bytes]:
        """Relay only visible deltas and exactly one browser-validated terminal envelope."""

        try:
            for event_name, event in self.client.agent_turn_stream(self.payload):
                if event_name == "delta":
                    if set(event) != {"type", "text"}:
                        raise AssistantServiceError("invalid_response")
                    text = event.get("text")
                    if (
                        not isinstance(text, str)
                        or not 1 <= len(text) <= _BROWSER_STREAM_DELTA_MAX_CHARS
                    ):
                        raise AssistantServiceError("invalid_response")
                    yield _sse_event("delta", {"type": "delta", "text": text})
                    continue

                if event_name != "final" or set(event) != {"type", "response"}:
                    raise AssistantServiceError("invalid_response")
                browser = _browser_agent(event.get("response"), self.turn_id)
                persisted = _persist_captured_chat_result(
                    self,
                    browser,
                    internal_workflow=(
                        "AGENT_FAILURE"
                        if browser["plan"]["state"] == "failed"
                        else "AGENT"
                    ),
                )
                yield _sse_event(
                    "final",
                    {"type": "final", "response": persisted},
                )
                return

            # EOF without the mandatory terminal event is an invalid inner stream.
            raise AssistantServiceError("invalid_response")
        except AssistantServiceError as error:
            failure = self.failure_result(_client_error_code(error.code))
        except Exception:  # noqa: BLE001 - the browser boundary remains sanitized
            failure = self.failure_result("service_unavailable")

        persisted = _persist_captured_chat_result(
            self,
            failure,
            internal_workflow="AGENT_FAILURE",
        )
        yield _sse_event(
            "final",
            {"type": "final", "response": persisted},
        )

    def failure_result(self, code: str) -> dict[str, object]:
        """Create a non-executable conversational failure for this exact turn."""

        return {
            "ok": True,
            "turn_id": str(self.turn_id),
            "workflow": "AGENT",
            "answer": _failure_answer(code),
            "confidence": "low",
            "limitations": [],
            "citations": [],
            "plan": dict(self.failure_plan),
            "conversation_id": self.conversation_id,
        }


class AssistantChatStreamBridge(models.AbstractModel):
    _inherit = "odoo.ai.assistant.bridge"

    @api.model
    def prepare_chat_stream(self, message, screen, conversation_id=None):
        """Capture all ORM-derived authority before returning a WSGI streaming iterator."""

        if not self.env.user._is_internal():
            raise ChatStreamPreparationError("access_denied")
        if not isinstance(screen, Mapping):
            raise ChatStreamPreparationError("invalid_context")
        try:
            normalized_message = _chat_message(message)
            parsed_conversation_id = _optional_uuid(conversation_id)
            prepared = prepare_agent_turn(
                env=self.env,
                screen_payload=screen,
                message=normalized_message,
            )
            payload = prepared.to_assistant_payload()
            policy = self._agent_policy_layers(
                parsed_conversation_id,
                normalized_message,
            )
            actor = self._chat_actor()
            payload.update(
                {
                    "actor": actor,
                    "conversation_id": parsed_conversation_id,
                    "policy_layers": policy["layers"],
                    "synthetic_data_authorized": policy[
                        "synthetic_data_authorized"
                    ],
                }
            )
            # _chat_client() is intentionally resolved while env/cursor are alive so the
            # effective per-user reasoning preference is captured before streaming starts.
            client = self._chat_client()
            failure_plan = _failure_plan(
                self,
                normalized_message,
                parsed_conversation_id,
            )
        except (TypeError, ValueError, TurnContextError):
            raise ChatStreamPreparationError("invalid_context") from None
        except AssistantServiceError as error:
            raise ChatStreamPreparationError(_client_error_code(error.code)) from None
        except Exception:  # noqa: BLE001 - sanitize the browser preparation boundary
            raise ChatStreamPreparationError("service_unavailable") from None

        return PreparedBrowserChatStream(
            client=client,
            payload=payload,
            turn_id=prepared.turn_id,
            actor=actor,
            message=normalized_message,
            conversation_id=parsed_conversation_id,
            failure_plan=failure_plan,
        )

    @api.model
    def chat_stream_preparation_failure(
        self,
        code,
        message,
        conversation_id=None,
    ):
        """Build/persist a plain fallback before the HTTP streaming iterator is returned."""

        normalized_code = code if isinstance(code, str) and code else "service_unavailable"
        normalized_message = _safe_message(message)
        parsed_conversation_id = _safe_conversation_id(conversation_id)
        result = {
            "ok": True,
            "turn_id": str(uuid4()),
            "workflow": "AGENT",
            "answer": _failure_answer(normalized_code),
            "confidence": "low",
            "limitations": [],
            "citations": [],
            "plan": _failure_plan(self, normalized_message, parsed_conversation_id),
            "conversation_id": parsed_conversation_id,
        }
        if not normalized_message:
            return result
        try:
            return self._persist_chat_result(
                result,
                message=normalized_message,
                conversation_id=parsed_conversation_id,
                internal_workflow="AGENT_FAILURE",
            )
        except Exception:  # noqa: BLE001 - fallback must survive history failures
            return result


def _persist_captured_chat_result(
    prepared: PreparedBrowserChatStream,
    response: dict[str, object],
    *,
    internal_workflow: str,
) -> dict[str, object]:
    """Persist through Assistant HTTP only; never touch Odoo ORM from the WSGI iterator."""

    result = dict(response)
    answer = result.get("answer")
    if not isinstance(answer, str) or not answer:
        return result
    try:
        stored = prepared.client.chat_append(
            {
                "actor": prepared.actor,
                "conversation_id": prepared.conversation_id,
                "user_message": prepared.message,
                "assistant_message": answer,
                "internal_workflow": internal_workflow,
            }
        )
        stored_id = stored.get("conversation_id") if isinstance(stored, dict) else None
        result["conversation_id"] = (
            stored_id
            if isinstance(stored_id, str) and _is_uuid(stored_id)
            else prepared.conversation_id
        )
    except AssistantServiceError:
        result["conversation_id"] = prepared.conversation_id
    return result


def _sse_event(event: str, payload: dict[str, object]) -> bytes:
    encoded = json.dumps(
        payload,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return f"event: {event}\ndata: {encoded}\n\n".encode()


def _safe_message(value) -> str:
    if not isinstance(value, str):
        return ""
    normalized = value.strip()
    return normalized[:4000] if normalized and "\x00" not in normalized else ""


def _safe_conversation_id(value) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        return _optional_uuid(value)
    except ValueError:
        return None
