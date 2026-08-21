"""Authenticated browser-to-Odoo bridge for the deterministic M2 panel."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from typing import Final

from odoo import api, models

from ..services import (
    AssistantServiceClient,
    AssistantServiceError,
    ScreenContextValidationError,
    TurnContextError,
    prepare_context_turn,
)

SERVICE_URL_PARAM: Final = "odoo_ai_assistant.service_url"
SECRET_FILE_PARAM: Final = "odoo_ai_assistant.shared_secret_file"
SERVICE_URL_ENV: Final = "ODOO_AI_SERVICE_URL"
SECRET_FILE_ENV: Final = "ODOO_AI_SHARED_SECRET_FILE"
EXPECTED_RESPONSE_KEYS: Final = frozenset(
    {
        "completed_at",
        "evidence",
        "fields_read",
        "instance_id",
        "instance_state",
        "message",
        "record",
        "status",
        "turn_id",
    }
)
ALLOWED_FIELDS: Final = frozenset(
    {"display_name", "name", "state", "company_id"}
)


class AssistantBridge(models.AbstractModel):
    _name = "odoo.ai.assistant.bridge"
    _description = "Odoo AI Assistant Context Bridge"

    @api.model
    def submit_context_read(self, message, screen):
        """Derive authority server-side and return only the sanitized UI result."""

        if not self.env.user._is_internal():
            return _error("access_denied")
        if not isinstance(screen, Mapping):
            return _error("invalid_context")
        try:
            prepared = prepare_context_turn(
                env=self.env,
                screen_payload=screen,
                message=message,
            )
            response = self._client().context_read(prepared.to_assistant_payload())
            return _browser_response(response, prepared)
        except ScreenContextValidationError:
            return _error("invalid_context")
        except TurnContextError as error:
            return _error(_turn_error_code(error.code))
        except AssistantServiceError as error:
            return _error(_client_error_code(error.code))
        # The RPC boundary must not expose unexpected server exception details.
        except Exception:  # noqa: BLE001
            return _error("service_unavailable")

    @api.model
    def _client(self):
        parameters = self.env["ir.config_parameter"]
        service_url = parameters._get_param(SERVICE_URL_PARAM) or os.environ.get(
            SERVICE_URL_ENV
        )
        secret_file = parameters._get_param(SECRET_FILE_PARAM) or os.environ.get(
            SECRET_FILE_ENV
        )
        if not service_url:
            raise AssistantServiceError("configuration_missing")
        return AssistantServiceClient(
            base_url=service_url,
            shared_secret_file=secret_file,
        )


def _browser_response(response, prepared):
    if not isinstance(response, dict) or set(response) != EXPECTED_RESPONSE_KEYS:
        raise AssistantServiceError("invalid_response")
    if (
        response.get("status") != "ok"
        or response.get("turn_id") != str(prepared.turn_id)
        or not isinstance(response.get("message"), str)
        or not 1 <= len(response["message"]) <= 512
    ):
        raise AssistantServiceError("invalid_response")
    fields_read = response.get("fields_read")
    record = response.get("record")
    if (
        not isinstance(fields_read, list)
        or not 1 <= len(fields_read) <= 4
        or len(fields_read) != len(set(fields_read))
        or not set(fields_read).issubset(ALLOWED_FIELDS)
        or not isinstance(record, dict)
        or set(record) != {"captured_at", "fields", "provenance", "record"}
    ):
        raise AssistantServiceError("invalid_response")
    reference = record.get("record")
    fields = record.get("fields")
    if (
        not isinstance(reference, dict)
        or set(reference) != {"display_name", "id", "model"}
        or reference.get("model") != prepared.screen.model
        or reference.get("id") != prepared.screen.res_id
        or (
            reference.get("display_name") is not None
            and not isinstance(reference.get("display_name"), str)
        )
        or not isinstance(fields, dict)
        or set(fields) != set(fields_read)
        or not isinstance(record.get("captured_at"), str)
    ):
        raise AssistantServiceError("invalid_response")
    result = {
        "ok": True,
        "turn_id": str(prepared.turn_id),
        "message": response["message"],
        "context": {
            "model": prepared.screen.model,
            "res_id": prepared.screen.res_id,
            "display_name": reference.get("display_name"),
            "captured_at": record["captured_at"],
        },
        "fields": fields,
    }
    serialized = json.dumps(
        result,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    if prepared.delegation_token in serialized:
        raise AssistantServiceError("invalid_response")
    return result


def _turn_error_code(code: str) -> str:
    if code in {
        "invalid_message",
        "model_unavailable",
    }:
        return "invalid_context"
    if code in {"delegation_unavailable", "delegation_unconfigured"}:
        return "service_unavailable"
    return "access_denied" if code == "superuser_delegation_forbidden" else "invalid_context"


def _client_error_code(code: str) -> str:
    if code == "access_denied":
        return "access_denied"
    if code in {
        "authentication_rejected",
        "authentication_unavailable",
        "authentication_unconfigured",
    }:
        return "authentication_failed"
    if code == "invalid_context":
        return "invalid_context"
    if code == "invalid_response":
        return "invalid_response"
    return "service_unavailable"


def _error(code: str) -> dict[str, object]:
    return {"error": {"code": code}, "ok": False}
