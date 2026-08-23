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
    derive_action_decision_actor,
    prepare_action_preview_turn,
    prepare_context_turn,
    prepare_how_to_turn,
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
ALLOWED_FIELDS: Final = frozenset({"display_name", "name", "state", "company_id"})
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
ALLOWED_WORKFLOWS: Final = frozenset({"EXPLAIN", "QUERY", "HOW_TO", "ACTION"})
EXPECTED_QUERY_RESPONSE_KEYS: Final = EXPECTED_EXPLAIN_RESPONSE_KEYS
EXPECTED_HOW_TO_RESPONSE_KEYS: Final = EXPECTED_EXPLAIN_RESPONSE_KEYS
EXPECTED_ACTION_RESPONSE_KEYS: Final = frozenset(
    {
        "answer_markdown",
        "completed_at",
        "confidence",
        "evidence_refs",
        "limitations",
        "proposal",
        "status",
        "turn_id",
        "workflow",
    }
)
EXPECTED_ACTION_DECISION_KEYS: Final = frozenset(
    {
        "approval_id",
        "attempt_id",
        "completed_at",
        "error_code",
        "evidence_id",
        "payload_fingerprint",
        "proposal_id",
        "state",
    }
)


class AssistantBridge(models.AbstractModel):
    _name = "odoo.ai.assistant.bridge"
    _description = "Odoo AI Assistant Context Bridge"

    @api.model
    def submit_turn(self, message, screen, workflow):
        """Select one read-only workflow before deriving its narrow authority."""

        if workflow not in ALLOWED_WORKFLOWS:
            return _error("invalid_workflow")
        handlers = {
            "EXPLAIN": self.submit_explain,
            "QUERY": self.submit_query,
            "HOW_TO": self.submit_how_to,
            "ACTION": self.submit_action,
        }
        return handlers[workflow](message, screen)

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
    def submit_how_to(self, message, screen):
        """Run HOW_TO with navigation/schema-only authority retained server-side."""

        if not self.env.user._is_internal():
            return _error("access_denied")
        if not isinstance(screen, Mapping):
            return _error("invalid_context")
        try:
            prepared = prepare_how_to_turn(
                env=self.env,
                screen_payload=screen,
                message=message,
            )
            response = self._client().how_to(prepared.to_assistant_payload())
            return _browser_how_to_response(response, prepared)
        except ScreenContextValidationError:
            return _error("invalid_context")
        except TurnContextError as error:
            return _error(_turn_error_code(error.code))
        except AssistantServiceError as error:
            return _error(_client_error_code(error.code))
        except Exception:  # noqa: BLE001 - sanitize the browser RPC boundary
            return _error("service_unavailable")

    @api.model
    def submit_action(self, message, screen):
        """Run preview-only ACTION with p1 authority retained server-side."""

        if not self.env.user._is_internal():
            return _error("access_denied")
        if not isinstance(screen, Mapping):
            return _error("invalid_context")
        try:
            prepared = prepare_action_preview_turn(
                env=self.env,
                screen_payload=screen,
                message=message,
            )
            response = self._client().action(prepared.to_assistant_payload())
            return _browser_action_response(response, prepared)
        except ScreenContextValidationError:
            return _error("invalid_context")
        except TurnContextError as error:
            return _error(_turn_error_code(error.code))
        except AssistantServiceError as error:
            return _error(_client_error_code(error.code))
        except Exception:  # noqa: BLE001 - sanitize the browser RPC boundary
            return _error("service_unavailable")

    @api.model
    def decide_action(self, proposal_id, decision):
        """Derive the actor in Odoo and send no editable payload to Assistant."""

        if not self.env.user._is_internal():
            return _error("access_denied")
        if not _uuid(proposal_id) or decision not in {"approve", "reject"}:
            return _error("invalid_context")
        try:
            response = self._client().action_decision(
                {
                    "proposal_id": proposal_id,
                    "decision": decision,
                    "actor": derive_action_decision_actor(self.env),
                }
            )
            return _browser_action_decision_response(response, proposal_id)
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
    if (
        not isinstance(response, dict)
        or set(response) != EXPECTED_EXPLAIN_RESPONSE_KEYS
    ):
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
        "workflow": "EXPLAIN",
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
        "workflow": "QUERY",
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


def _browser_action_response(response, prepared):
    if not isinstance(response, dict) or set(response) != EXPECTED_ACTION_RESPONSE_KEYS:
        raise AssistantServiceError("invalid_response")
    answer = response.get("answer_markdown")
    limitations = response.get("limitations")
    references = response.get("evidence_refs")
    proposal = response.get("proposal")
    if (
        response.get("status") != "ok"
        or response.get("workflow") != "ACTION"
        or response.get("turn_id") != str(prepared.turn_id)
        or response.get("confidence") not in ALLOWED_CONFIDENCE
        or not _bounded_text(answer, 16_384, require_nonempty=True)
        or not isinstance(response.get("completed_at"), str)
        or not isinstance(limitations, list)
        or len(limitations) > 8
        or any(
            not _bounded_text(value, 1_024, require_nonempty=True)
            for value in limitations
        )
        or not isinstance(references, list)
        or len(references) > 8
        or len(references) != len(set(references))
        or any(not _uuid(value) for value in references)
    ):
        raise AssistantServiceError("invalid_response")
    sanitized_proposal = (
        None
        if proposal is None
        else _browser_action_proposal(proposal, prepared, references)
    )
    result = {
        "ok": True,
        "turn_id": str(prepared.turn_id),
        "workflow": "ACTION",
        "answer": answer,
        "confidence": response["confidence"],
        "limitations": list(limitations),
        "proposal": sanitized_proposal,
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


def _browser_action_proposal(proposal, prepared, references):
    if isinstance(proposal, dict) and proposal.get("action_kind") == "record_create":
        return _browser_action_create_proposal(proposal, prepared, references)
    if isinstance(proposal, dict) and proposal.get("action_kind") == "business_action":
        return _browser_business_action_proposal(proposal, prepared, references)
    expected = {
        "changes",
        "evidence_id",
        "expires_at",
        "payload_fingerprint",
        "precondition_fingerprint",
        "proposal_id",
        "target",
        "turn_id",
        "warnings",
    }
    if not isinstance(proposal, dict) or set(proposal) != expected:
        raise AssistantServiceError("invalid_response")
    target = proposal.get("target")
    changes = proposal.get("changes")
    warnings = proposal.get("warnings")
    if (
        not _uuid(proposal.get("proposal_id"))
        or proposal.get("turn_id") != str(prepared.turn_id)
        or not isinstance(proposal.get("payload_fingerprint"), str)
        or _ACTION_FINGERPRINT.fullmatch(proposal["payload_fingerprint"]) is None
        or not isinstance(proposal.get("precondition_fingerprint"), str)
        or _ACTION_FINGERPRINT.fullmatch(proposal["precondition_fingerprint"]) is None
        or not _uuid(proposal.get("evidence_id"))
        or proposal["evidence_id"] not in references
        or not isinstance(proposal.get("expires_at"), str)
        or not isinstance(target, dict)
        or set(target) != {"model", "record_id"}
        or target.get("model") != prepared.screen.model
        or target.get("record_id") != prepared.screen.res_id
        or not isinstance(changes, list)
        or not 1 <= len(changes) <= 4
        or not isinstance(warnings, list)
        or len(warnings) > 8
        or any(
            not _bounded_text(value, 512, require_nonempty=True) for value in warnings
        )
    ):
        raise AssistantServiceError("invalid_response")
    sanitized_changes = [_browser_action_change(value) for value in changes]
    fields = [value["field"] for value in sanitized_changes]
    if len(fields) != len(set(fields)) or not set(fields).issubset(
        prepared.allowed_fields
    ):
        raise AssistantServiceError("invalid_response")
    return {
        "proposal_id": proposal["proposal_id"],
        "target": dict(target),
        "changes": sanitized_changes,
        "warnings": list(warnings),
        "expires_at": proposal["expires_at"],
    }


def _browser_action_create_proposal(proposal, prepared, references):
    expected = {
        "action_kind",
        "evidence_id",
        "expires_at",
        "payload_fingerprint",
        "precondition_fingerprint",
        "proposal_id",
        "target",
        "turn_id",
        "values",
        "warnings",
    }
    target = proposal.get("target")
    values = proposal.get("values")
    warnings = proposal.get("warnings")
    if (
        not isinstance(proposal, dict)
        or set(proposal) != expected
        or proposal.get("action_kind") != "record_create"
        or not _uuid(proposal.get("proposal_id"))
        or proposal.get("turn_id") != str(prepared.turn_id)
        or not isinstance(proposal.get("payload_fingerprint"), str)
        or _ACTION_FINGERPRINT.fullmatch(proposal["payload_fingerprint"]) is None
        or not isinstance(proposal.get("precondition_fingerprint"), str)
        or _ACTION_FINGERPRINT.fullmatch(proposal["precondition_fingerprint"]) is None
        or not _uuid(proposal.get("evidence_id"))
        or proposal["evidence_id"] not in references
        or not isinstance(proposal.get("expires_at"), str)
        or not isinstance(target, dict)
        or set(target) != {"model"}
        or target.get("model") != prepared.screen.model
        or not isinstance(values, list)
        or not 1 <= len(values) <= 4
        or not isinstance(warnings, list)
        or len(warnings) > 8
        or any(
            not _bounded_text(value, 512, require_nonempty=True) for value in warnings
        )
    ):
        raise AssistantServiceError("invalid_response")
    sanitized_values = []
    fields = set()
    for value in values:
        if (
            not isinstance(value, dict)
            or set(value) != {"field", "label", "value"}
            or not _identifier(value.get("field"), 128)
            or value.get("label") is not None
            and not _identifier(value.get("label"), 256)
            or value["field"] in fields
        ):
            raise AssistantServiceError("invalid_response")
        fields.add(value["field"])
        sanitized_values.append(
            {
                "field": value["field"],
                "label": value["label"],
                "value": _browser_action_value(value.get("value")),
            }
        )
    if not fields.issubset(prepared.allowed_fields):
        raise AssistantServiceError("invalid_response")
    return {
        "action_kind": "record_create",
        "proposal_id": proposal["proposal_id"],
        "target": dict(target),
        "values": sanitized_values,
        "warnings": list(warnings),
        "expires_at": proposal["expires_at"],
    }


def _browser_business_action_proposal(proposal, prepared, references):
    expected = {
        "action_id",
        "action_kind",
        "display_name",
        "evidence_id",
        "expected_states",
        "expires_at",
        "payload_fingerprint",
        "precondition_fingerprint",
        "proposal_id",
        "state_before",
        "target",
        "turn_id",
        "warnings",
    }
    target = proposal.get("target")
    warnings = proposal.get("warnings")
    if (
        not isinstance(proposal, dict)
        or set(proposal) != expected
        or proposal.get("action_kind") != "business_action"
        or proposal.get("action_id") != "sale.order.confirm.v1"
        or not _uuid(proposal.get("proposal_id"))
        or proposal.get("turn_id") != str(prepared.turn_id)
        or not isinstance(proposal.get("payload_fingerprint"), str)
        or _ACTION_FINGERPRINT.fullmatch(proposal["payload_fingerprint"]) is None
        or not isinstance(proposal.get("precondition_fingerprint"), str)
        or _ACTION_FINGERPRINT.fullmatch(proposal["precondition_fingerprint"]) is None
        or not _uuid(proposal.get("evidence_id"))
        or proposal["evidence_id"] not in references
        or not isinstance(proposal.get("expires_at"), str)
        or not isinstance(target, dict)
        or set(target) != {"model", "record_id"}
        or target != {"model": "sale.order", "record_id": prepared.screen.res_id}
        or prepared.screen.model != "sale.order"
        or not _bounded_text(proposal.get("display_name"), 256, require_nonempty=True)
        or proposal.get("state_before") not in {"draft", "sent"}
        or proposal.get("expected_states") != ["sale", "done"]
        or not isinstance(warnings, list)
        or len(warnings) > 8
        or any(
            not _bounded_text(value, 512, require_nonempty=True) for value in warnings
        )
    ):
        raise AssistantServiceError("invalid_response")
    return {
        "action_id": "sale.order.confirm.v1",
        "action_kind": "business_action",
        "display_name": proposal["display_name"],
        "expected_states": ["sale", "done"],
        "expires_at": proposal["expires_at"],
        "proposal_id": proposal["proposal_id"],
        "state_before": proposal["state_before"],
        "target": dict(target),
        "warnings": list(warnings),
    }


def _browser_action_change(change):
    if (
        not isinstance(change, dict)
        or set(change) != {"after", "before", "field", "label"}
        or not _identifier(change.get("field"), 128)
        or change.get("label") is not None
        and not _identifier(change.get("label"), 256)
    ):
        raise AssistantServiceError("invalid_response")
    return {
        "field": change["field"],
        "label": change["label"],
        "before": _browser_action_value(change.get("before")),
        "after": _browser_action_value(change.get("after")),
    }


def _browser_action_value(value):
    if not isinstance(value, dict) or set(value) != {"kind", "value"}:
        raise AssistantServiceError("invalid_response")
    kind = value.get("kind")
    item = value.get("value")
    valid = item is None
    if kind == "boolean":
        valid = valid or isinstance(item, bool)
    elif kind in {"integer", "many2one"}:
        valid = valid or type(item) is int and (kind == "integer" or item > 0)
    elif kind in {"date", "datetime", "decimal", "selection", "text"}:
        valid = valid or _bounded_text(item, 4_000)
    else:
        valid = False
    if not valid:
        raise AssistantServiceError("invalid_response")
    return {"kind": kind, "value": item}


def _browser_action_decision_response(response, proposal_id):
    if not isinstance(response, dict) or set(response) != EXPECTED_ACTION_DECISION_KEYS:
        raise AssistantServiceError("invalid_response")
    state = response.get("state")
    allowed = {
        "rejected",
        "verified",
        "stale",
        "failed",
        "execution_unknown",
        "committed_unverified",
    }
    approval_id = response.get("approval_id")
    attempt_id = response.get("attempt_id")
    evidence_id = response.get("evidence_id")
    error_code = response.get("error_code")
    if (
        response.get("proposal_id") != proposal_id
        or state not in allowed
        or not isinstance(response.get("payload_fingerprint"), str)
        or _ACTION_FINGERPRINT.fullmatch(response["payload_fingerprint"]) is None
        or not isinstance(response.get("completed_at"), str)
        or (approval_id is not None and not _uuid(approval_id))
        or (attempt_id is not None and not _uuid(attempt_id))
        or (evidence_id is not None and not _uuid(evidence_id))
        or (error_code is not None and not _identifier(error_code, 128))
        or state == "rejected"
        and (
            approval_id is not None or attempt_id is not None or evidence_id is not None
        )
        or state != "rejected"
        and (approval_id is None or attempt_id is None)
        or state == "verified"
        and (evidence_id is None or error_code is not None)
        or state != "verified"
        and evidence_id is not None
    ):
        raise AssistantServiceError("invalid_response")
    return {
        "ok": True,
        "proposal_id": proposal_id,
        "state": state,
        "completed_at": response["completed_at"],
        "approval_id": approval_id,
        "attempt_id": attempt_id,
        "evidence_id": evidence_id,
        "error_code": error_code,
    }


def _browser_how_to_response(response, prepared):
    if not isinstance(response, dict) or set(response) != EXPECTED_HOW_TO_RESPONSE_KEYS:
        raise AssistantServiceError("invalid_response")
    answer = response.get("answer_markdown")
    limitations = response.get("limitations")
    citations = response.get("citations")
    if (
        response.get("status") != "ok"
        or response.get("workflow") != "HOW_TO"
        or response.get("turn_id") != str(prepared.turn_id)
        or response.get("confidence") not in ALLOWED_CONFIDENCE
        or not isinstance(answer, str)
        or not 1 <= len(answer) <= 16_384
        or not isinstance(response.get("completed_at"), str)
        or not isinstance(limitations, list)
        or len(limitations) > 8
        or any(not _identifier(value, 1_024) for value in limitations)
        or not isinstance(citations, list)
        or len(citations) > 24
    ):
        raise AssistantServiceError("invalid_response")
    sanitized = [_browser_how_to_citation(value, prepared) for value in citations]
    evidence_ids = [value["evidence_id"] for value in sanitized]
    if len(evidence_ids) != len(set(evidence_ids)):
        raise AssistantServiceError("invalid_response")
    result = {
        "ok": True,
        "turn_id": str(prepared.turn_id),
        "workflow": "HOW_TO",
        "answer": answer,
        "confidence": response["confidence"],
        "limitations": list(limitations),
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


def _browser_how_to_citation(citation, prepared):
    if not isinstance(citation, dict) or not _uuid(citation.get("evidence_id")):
        raise AssistantServiceError("invalid_response")
    kind = citation.get("kind")
    if kind == "navigation":
        expected = {
            "captured_at",
            "evidence_id",
            "kind",
            "menu_id",
            "path",
            "target_model",
            "view_modes",
        }
        path = citation.get("path")
        view_modes = citation.get("view_modes")
        if (
            set(citation) != expected
            or type(citation.get("menu_id")) is not int
            or citation["menu_id"] <= 0
            or not isinstance(path, list)
            or not 1 <= len(path) <= 8
            or any(not _identifier(value, 256) for value in path)
            or citation.get("target_model") not in {None, prepared.screen.model}
            or not isinstance(view_modes, list)
            or len(view_modes) > 7
            or any(
                value
                not in {
                    "activity",
                    "calendar",
                    "form",
                    "graph",
                    "kanban",
                    "list",
                    "pivot",
                }
                for value in view_modes
            )
            or not isinstance(citation.get("captured_at"), str)
        ):
            raise AssistantServiceError("invalid_response")
        return dict(citation)
    if kind == "schema":
        expected = {
            "captured_at",
            "evidence_id",
            "fields",
            "kind",
            "model",
            "schema_id",
        }
        fields = citation.get("fields")
        if (
            set(citation) != expected
            or citation.get("model") != prepared.screen.model
            or not isinstance(citation.get("schema_id"), str)
            or _FINGERPRINT.fullmatch(citation["schema_id"]) is None
            or not isinstance(fields, list)
            or not 1 <= len(fields) <= 64
            or any(not _browser_schema_field(value) for value in fields)
            or not isinstance(citation.get("captured_at"), str)
        ):
            raise AssistantServiceError("invalid_response")
        return dict(citation)
    if kind == "document":
        expected = {
            "document_id",
            "end_line",
            "evidence_id",
            "fingerprint",
            "kind",
            "locale",
            "media_type",
            "ordinal",
            "provider_id",
            "start_line",
            "title",
        }
        if (
            set(citation) != expected
            or not isinstance(citation.get("provider_id"), str)
            or re.fullmatch(
                r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", citation["provider_id"]
            )
            is None
            or not _logical_path(citation.get("document_id"))
            or not _identifier(citation.get("title"), 512)
            or citation.get("locale") is not None
            and (
                not isinstance(citation.get("locale"), str)
                or re.fullmatch(
                    r"[A-Za-z]{2,8}(?:[-_][A-Za-z0-9]{1,8})*",
                    citation["locale"],
                )
                is None
            )
            or citation.get("media_type") not in {"text/markdown", "text/plain"}
            or type(citation.get("ordinal")) is not int
            or not 0 <= citation["ordinal"] <= 65_535
            or type(citation.get("start_line")) is not int
            or type(citation.get("end_line")) is not int
            or citation["start_line"] <= 0
            or citation["end_line"] < citation["start_line"]
            or not isinstance(citation.get("fingerprint"), str)
            or _FINGERPRINT.fullmatch(citation["fingerprint"]) is None
        ):
            raise AssistantServiceError("invalid_response")
        return dict(citation)
    raise AssistantServiceError("invalid_response")


_FINGERPRINT = re.compile(r"sha256:[0-9a-f]{64}")
_ACTION_FINGERPRINT = re.compile(r"[a-z][a-z0-9_-]{0,31}:v[0-9]+:sha256:[0-9a-f]{64}")


def _browser_schema_field(value):
    return (
        isinstance(value, dict)
        and set(value) == {"field_type", "label", "name"}
        and _identifier(value.get("name"), 128)
        and _identifier(value.get("field_type"), 128)
        and (value.get("label") is None or _identifier(value.get("label"), 256))
    )


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
            or re.fullmatch(r"sha256:[0-9a-f]{64}", citation["fingerprint"]) is None
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


def _bounded_text(value, max_length, *, require_nonempty=False):
    return (
        isinstance(value, str)
        and (len(value) >= 1 if require_nonempty else True)
        and len(value) <= max_length
        and all(ord(character) >= 32 or character in "\t\n\r" for character in value)
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
    return (
        "access_denied"
        if code == "superuser_delegation_forbidden"
        else "invalid_context"
    )


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
        "action_budget_exceeded",
        "action_rejected",
        "approval_binding_mismatch",
        "approval_expired",
        "approval_not_found",
        "engine_timeout",
        "engine_unavailable",
        "evidence_unavailable",
        "query_budget_exceeded",
        "query_rejected",
        "proposal_already_decided",
        "proposal_not_found",
        "record_context_required",
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
