"""History mutation facade for the product chat UI."""

from __future__ import annotations

from uuid import UUID

from odoo import api, models

from ..services import AssistantServiceError
from .assistant_bridge import _client_error_code, _error


class AssistantChatHistoryActions(models.AbstractModel):
    _inherit = "odoo.ai.assistant.bridge"

    @api.model
    def delete_chat_conversations(self, conversation_ids):
        if not self.env.user._is_internal():
            return _error("access_denied")
        try:
            parsed_ids = _conversation_ids(conversation_ids)
            response = self._chat_client().chat_delete(
                {
                    "actor": self._chat_actor(),
                    "conversation_ids": parsed_ids,
                }
            )
            if (
                not isinstance(response, dict)
                or set(response) != {"deleted_count"}
                or type(response.get("deleted_count")) is not int
                or response["deleted_count"] != len(parsed_ids)
            ):
                raise AssistantServiceError("invalid_response")
            return {"ok": True, "deleted_count": response["deleted_count"]}
        except ValueError:
            return _error("invalid_context")
        except AssistantServiceError as error:
            if error.code == "conversation_not_found":
                return _error("invalid_context")
            return _error(_client_error_code(error.code))
        except Exception:  # noqa: BLE001 - browser boundary stays sanitized
            return _error("service_unavailable")


def _conversation_ids(value) -> list[str]:
    if not isinstance(value, list) or not 1 <= len(value) <= 50:
        raise ValueError
    parsed: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise TypeError
        parsed.append(str(UUID(item)))
    if len(set(parsed)) != len(parsed):
        raise ValueError
    return parsed
