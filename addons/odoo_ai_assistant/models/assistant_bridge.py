"""Authenticated browser-to-Odoo bridge for the deterministic M2 panel."""

from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping
from pathlib import PurePosixPath
from typing import Final
from uuid import UUID

from odoo import api, models

from ..services import (
    AssistantServiceClient,
    AssistantServiceError,
    ScreenContextValidationError,
    TurnContextError,
    prepare_context_turn,
    prepare_query_turn,
)

SERVICE_URL_PARAM: Final = "odoo_ai_assistant.service_url"
SECRET_FILE_PARAM: Final = "odoo_ai_assistant.shared_secret_file"
TURN_TIMEOUT_PARAM: Final = "odoo_ai_assistant.turn_timeout_seconds"
SERVICE_URL_ENV: Final = "ODOO_AI_SERVICE_URL"
SECRET_FILE_ENV: Final = "ODOO_AI_SHARED_SECRET_FILE"
TURN_TIMEOUT_ENV: Final = "ODOO_AI_TURN_TIMEOUT_SECONDS"
DEFAULT_TURN_TIMEOUT_SECONDS: Final = 150.0
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
EXPECTED_EXPLAIN_RESPONSE_KEYS: Final = frozenset(
    {
        "answer_markdown",
        "citations",
        "completed_at",
        "confidence",
        "limitations",
        "status",
        "turn_id",
        "workflow",
    }
)
ALLOWED_CONFIDENCE: Final = frozenset({"high", "medium", "low"})
EXPECTED_QUERY_RESPONSE_KEYS: Final = EXPECTED_EXPLAIN_RESPONSE_KEYS


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
    def submit_explain(self, message, screen):
        """Run M4 EXPLAIN while retaining identity and transport server-side."""

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
            response = self._client().explain(prepared.to_assistant_payload())
            return _browser_explain_response(response, prepared)
        except ScreenContextValidationError:
            return _error("invalid_context")
        except TurnContextError as error:
            return _error(_turn_error_code(error.code))
        except AssistantServiceError as error:
            return _error(_client_error_code(error.code))
        except Exception:  # noqa: BLE001 - sanitize the browser RPC boundary
            return _error("service_unavailable")

    @api.model
    def submit_query(self, message, screen):
        """Run M5 QUERY with q1 authority retained entirely server-side."""

        if not self.env.user._is_internal():
            return _error("access_denied")
        if not isinstance(screen, Mapping):
            return _error("invalid_context")
        try:
            prepared = prepare_query_turn(
                env=self.env,
                screen_payload=screen,
                message=message,
            )
            response = self._client().query(prepared.to_assistant_payload())
            return _browser_query_response(response, prepared)
        except ScreenContextValidationError:
            return _error("invalid_context")
        except TurnContextError as error:
            return _error(_turn_error_code(error.code))
        except AssistantServiceError as error:
            return _error(_client_error_code(error.code))
        except Exception:  # noqa: BLE001 - sanitize the browser RPC boundary
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
        timeout = _turn_timeout(
            parameters._get_param(TURN_TIMEOUT_PARAM)
            or os.environ.get(TURN_TIMEOUT_ENV)
        )
        if not service_url:
            raise AssistantServiceError("configuration_missing")
        return AssistantServiceClient(
            base_url=service_url,
            shared_secret_file=secret_file,
            timeout=timeout,
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


def _browser_explain_response(response, prepared):
    if not isinstance(response, dict) or set(response) != EXPECTED_EXPLAIN_RESPONSE_KEYS:
        raise AssistantServiceError("invalid_response")
    answer = response.get("answer_markdown")
    limitations = response.get("limitations")
    citations = response.get("citations")
    if (
        response.get("status") != "ok"
        or response.get("workflow") != "EXPLAIN"
        or response.get("turn_id") != str(prepared.turn_id)
        or response.get("confidence") not in ALLOWED_CONFIDENCE
        or not isinstance(answer, str)
        or not 1 <= len(answer) <= 16_384
        or not isinstance(response.get("completed_at"), str)
        or not isinstance(limitations, list)
        or len(limitations) > 8
        or any(
            not isinstance(value, str) or not 1 <= len(value) <= 1_024
            for value in limitations
        )
        or not isinstance(citations, list)
        or len(citations) > 24
    ):
        raise AssistantServiceError("invalid_response")
    sanitized_citations = [
        _browser_citation(citation, prepared) for citation in citations
    ]
    evidence_ids = [citation["evidence_id"] for citation in sanitized_citations]
    if len(evidence_ids) != len(set(evidence_ids)):
        raise AssistantServiceError("invalid_response")
    result = {
        "ok": True,
        "turn_id": str(prepared.turn_id),
        "answer": answer,
        "confidence": response["confidence"],
        "limitations": limitations,
        "citations": sanitized_citations,
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


def _browser_query_response(response, prepared):
    if not isinstance(response, dict) or set(response) != EXPECTED_QUERY_RESPONSE_KEYS:
        raise AssistantServiceError("invalid_response")
    answer = response.get("answer_markdown")
    limitations = response.get("limitations")
    citations = response.get("citations")
    if (
        response.get("status") != "ok"
        or response.get("workflow") != "QUERY"
        or response.get("turn_id") != str(prepared.turn_id)
        or response.get("confidence") not in ALLOWED_CONFIDENCE
        or not isinstance(answer, str)
        or not 1 <= len(answer) <= 16_384
        or not isinstance(response.get("completed_at"), str)
        or not isinstance(limitations, list)
        or len(limitations) > 8
        or any(
            not isinstance(value, str) or not 1 <= len(value) <= 1_024
            for value in limitations
        )
        or not isinstance(citations, list)
        or not 1 <= len(citations) <= 8
    ):
        raise AssistantServiceError("invalid_response")
    sanitized = [_browser_query_citation(value, prepared) for value in citations]
    evidence_ids = [value["evidence_id"] for value in sanitized]
    if len(evidence_ids) != len(set(evidence_ids)):
        raise AssistantServiceError("invalid_response")
    result = {
        "ok": True,
        "turn_id": str(prepared.turn_id),
        "answer": answer,
        "confidence": response["confidence"],
        "limitations": limitations,
        "citations": sanitized,
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


def _browser_query_citation(citation, prepared):
    expected = {
        "captured_at",
        "empty",
        "evidence_id",
        "kind",
        "limit",
        "model",
        "operation",
        "returned_count",
        "truncated",
    }
    if (
        not isinstance(citation, dict)
        or set(citation) != expected
        or citation.get("kind") != "query"
        or citation.get("model") != prepared.screen.model
        or citation.get("operation") not in {"query_records", "aggregate_records"}
        or not _uuid(citation.get("evidence_id"))
        or not isinstance(citation.get("captured_at"), str)
        or type(citation.get("returned_count")) is not int
        or not 0 <= citation["returned_count"] <= 50
        or type(citation.get("limit")) is not int
        or not 1 <= citation["limit"] <= 50
        or not isinstance(citation.get("truncated"), bool)
        or not isinstance(citation.get("empty"), bool)
    ):
        raise AssistantServiceError("invalid_response")
    return dict(citation)


def _browser_citation(citation, prepared):
    if not isinstance(citation, dict):
        raise AssistantServiceError("invalid_response")
    if citation.get("kind") == "record":
        expected = {
            "captured_at",
            "display_name",
            "evidence_id",
            "id",
            "kind",
            "model",
        }
        if (
            set(citation) != expected
            or citation.get("model") != prepared.screen.model
            or citation.get("id") != prepared.screen.res_id
            or (
                citation.get("display_name") is not None
                and not isinstance(citation.get("display_name"), str)
            )
            or not isinstance(citation.get("captured_at"), str)
            or not _uuid(citation.get("evidence_id"))
        ):
            raise AssistantServiceError("invalid_response")
        return dict(citation)
    if citation.get("kind") == "source":
        expected = {
            "end_line",
            "evidence_id",
            "fingerprint",
            "kind",
            "logical_path",
            "module",
            "provenance",
            "start_line",
        }
        start_line = citation.get("start_line")
        end_line = citation.get("end_line")
        if (
            set(citation) != expected
            or not _uuid(citation.get("evidence_id"))
            or not _identifier(citation.get("module"), 255)
            or not _logical_path(citation.get("logical_path"))
            or type(start_line) is not int
            or type(end_line) is not int
            or start_line <= 0
            or end_line < start_line
            or not isinstance(citation.get("fingerprint"), str)
            or re.fullmatch(r"sha256:[0-9a-f]{64}", citation["fingerprint"])
            is None
            or not _identifier(citation.get("provenance"), 64)
        ):
            raise AssistantServiceError("invalid_response")
        return dict(citation)
    raise AssistantServiceError("invalid_response")


def _uuid(value):
    if not isinstance(value, str):
        return False
    try:
        return str(UUID(value)) == value
    except ValueError:
        return False


def _identifier(value, max_length):
    return (
        isinstance(value, str)
        and 1 <= len(value) <= max_length
        and value == value.strip()
        and all(ord(character) >= 32 for character in value)
    )


def _logical_path(value):
    if not isinstance(value, str) or not 1 <= len(value) <= 1_024 or "\\" in value:
        return False
    path = PurePosixPath(value)
    return (
        not path.is_absolute()
        and str(path) == value
        and all(part not in {"", ".", ".."} for part in path.parts)
    )


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
    if code in {
        "engine_timeout",
        "engine_unavailable",
        "evidence_unavailable",
        "query_budget_exceeded",
    }:
        return code
    return "service_unavailable"


def _error(code: str) -> dict[str, object]:
    return {"error": {"code": code}, "ok": False}


def _turn_timeout(value: object) -> float:
    if value in (None, ""):
        return DEFAULT_TURN_TIMEOUT_SECONDS
    if isinstance(value, bool):
        raise AssistantServiceError("configuration_invalid")
    try:
        timeout = float(value)
    except (TypeError, ValueError):
        raise AssistantServiceError("configuration_invalid") from None
    if not 1 <= timeout <= 300:
        raise AssistantServiceError("configuration_invalid")
    return timeout
