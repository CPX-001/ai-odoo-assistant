"""Phase 11 durable CSV import capabilities."""

from __future__ import annotations

from odoo.exceptions import AccessError, UserError, ValidationError

from ..contracts import (
    CapabilityApproval,
    CapabilityContext,
    CapabilityEffect,
    CapabilityError,
    CapabilityExposure,
    CapabilityPreview,
    CapabilityRisk,
    CapabilityVerification,
)
from ..decorators import tool
from ....models.data_import import DataImportWorkflowError

_MAX_MAPPING_ITEMS = 64
_DEFAULT_CHUNK_SIZE = 250

_INSPECT_INPUT = {
    "type": "object",
    "properties": {
        "attachment_id": {"type": "integer", "minimum": 1},
        "model": {"type": "string", "minLength": 1, "maxLength": 128},
    },
    "required": ["attachment_id", "model"],
    "additionalProperties": False,
}
_FIELD = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "label": {"type": "string"},
        "type": {"type": "string"},
        "required": {"type": "boolean"},
    },
    "required": ["name", "label", "type", "required"],
    "additionalProperties": False,
}
_COLUMN = {
    "type": "object",
    "properties": {
        "column_index": {"type": "integer"},
        "column": {"type": "string"},
        "examples": {
            "type": "array",
            "maxItems": 3,
            "items": {"type": "string"},
        },
    },
    "required": ["column_index", "column", "examples"],
    "additionalProperties": False,
}
_MAPPING_ITEM = {
    "type": "object",
    "properties": {
        "column_index": {"type": "integer", "minimum": 0, "maximum": 63},
        "field": {"type": "string", "minLength": 1, "maxLength": 128},
    },
    "required": ["column_index", "field"],
    "additionalProperties": False,
}
_MAPPING_RESULT = {
    "type": "object",
    "properties": {
        "column_index": {"type": "integer"},
        "column": {"type": "string"},
        "field": {"type": "string"},
    },
    "required": ["column_index", "column", "field"],
    "additionalProperties": False,
}
_INSPECT_OUTPUT = {
    "type": "object",
    "properties": {
        "attachment_id": {"type": "integer"},
        "filename": {"type": "string"},
        "mimetype": {"type": "string"},
        "size": {"type": "integer"},
        "fingerprint": {"type": "string"},
        "target_model": {"type": "string"},
        "headers": {"type": "array", "maxItems": 64, "items": {"type": "string"}},
        "columns": {"type": "array", "maxItems": 64, "items": _COLUMN},
        "safe_fields": {"type": "array", "maxItems": 64, "items": _FIELD},
        "suggested_mapping": {
            "type": "array",
            "maxItems": 64,
            "items": _MAPPING_RESULT,
        },
        "estimated_rows": {"type": "integer"},
    },
    "required": [
        "attachment_id",
        "filename",
        "mimetype",
        "size",
        "fingerprint",
        "target_model",
        "headers",
        "columns",
        "safe_fields",
        "suggested_mapping",
        "estimated_rows",
    ],
    "additionalProperties": False,
}
_START_INPUT = {
    "type": "object",
    "properties": {
        "attachment_id": {"type": "integer", "minimum": 1},
        "model": {"type": "string", "minLength": 1, "maxLength": 128},
        "mapping": {
            "type": "array",
            "minItems": 1,
            "maxItems": _MAX_MAPPING_ITEMS,
            "items": _MAPPING_ITEM,
        },
        "chunk_size": {
            "type": "integer",
            "minimum": 1,
            "maximum": 1000,
            "default": _DEFAULT_CHUNK_SIZE,
        },
    },
    "required": ["attachment_id", "model", "mapping"],
    "additionalProperties": False,
}
_START_OUTPUT = {
    "type": "object",
    "properties": {
        "session_uuid": {"type": "string"},
        "state": {"type": "string"},
        "target_model": {"type": "string"},
        "filename": {"type": "string"},
        "total_rows": {"type": "integer"},
        "duplicate_rows": {"type": "integer"},
        "chunk_size": {"type": "integer"},
        "mapping_fingerprint": {"type": "string"},
    },
    "required": [
        "session_uuid",
        "state",
        "target_model",
        "filename",
        "total_rows",
        "duplicate_rows",
        "chunk_size",
        "mapping_fingerprint",
    ],
    "additionalProperties": False,
}
_STATUS_INPUT = {
    "type": "object",
    "properties": {
        "session_uuid": {"type": "string", "minLength": 32, "maxLength": 32},
        "recent_chunks": {"type": "integer", "minimum": 1, "maximum": 20, "default": 8},
    },
    "required": ["session_uuid"],
    "additionalProperties": False,
}
_STATUS_CHUNK = {
    "type": "object",
    "properties": {
        "sequence": {"type": "integer"},
        "row_start": {"type": "integer"},
        "row_end": {"type": "integer"},
        "input_count": {"type": "integer"},
        "imported_count": {"type": "integer"},
        "failed_count": {"type": "integer"},
        "state": {"type": "string"},
        "record_ids": {"type": "array", "maxItems": 1000, "items": {"type": "integer"}},
        "messages": {
            "type": "array",
            "maxItems": 8,
            "items": {
                "type": "object",
                "properties": {"type": {"type": "string"}, "message": {"type": "string"}},
                "required": ["type", "message"],
                "additionalProperties": False,
            },
        },
        "receipt_fingerprint": {"type": "string"},
        "completed_at": {"type": "string"},
    },
    "required": [
        "sequence",
        "row_start",
        "row_end",
        "input_count",
        "imported_count",
        "failed_count",
        "state",
        "record_ids",
        "messages",
        "receipt_fingerprint",
        "completed_at",
    ],
    "additionalProperties": False,
}
_STATUS_OUTPUT = {
    "type": "object",
    "properties": {
        "session_uuid": {"type": "string"},
        "state": {"type": "string"},
        "target_model": {"type": "string"},
        "filename": {"type": "string"},
        "total_rows": {"type": "integer"},
        "imported_rows": {"type": "integer"},
        "failed_rows": {"type": "integer"},
        "corrected_rows": {"type": "integer"},
        "remaining_rows": {"type": "integer"},
        "duplicate_rows": {"type": "integer"},
        "chunk_size": {"type": "integer"},
        "chunk_count": {"type": "integer"},
        "mapping_fingerprint": {"type": "string"},
        "last_error_code": {"type": "string"},
        "last_error_summary": {"type": "string"},
        "chunks": {"type": "array", "maxItems": 20, "items": _STATUS_CHUNK},
    },
    "required": [
        "session_uuid",
        "state",
        "target_model",
        "filename",
        "total_rows",
        "imported_rows",
        "failed_rows",
        "corrected_rows",
        "remaining_rows",
        "duplicate_rows",
        "chunk_size",
        "chunk_count",
        "mapping_fingerprint",
        "last_error_code",
        "last_error_summary",
        "chunks",
    ],
    "additionalProperties": False,
}


def _turn_bound(context: CapabilityContext):
    try:
        turn = context.env["odoo.ai.turn"].search(
            [
                ("turn_uuid", "=", context.turn_id),
                ("user_id", "=", context.env.uid),
                ("company_id", "=", context.env.company.id),
            ],
            limit=1,
        )
    except Exception as error:  # noqa: BLE001 - turn binding fails closed
        raise CapabilityError("data_import_turn_binding_invalid") from error
    if not turn:
        raise CapabilityError("data_import_turn_binding_invalid")
    return turn


def _inspect(context: CapabilityContext, arguments):
    _turn_bound(context)
    try:
        result = context.env["odoo.ai.data.import.session"].inspect_csv_attachment(
            turn_uuid=context.turn_id,
            attachment_id=arguments.get("attachment_id"),
            target_model=arguments.get("model"),
        )
    except (DataImportWorkflowError, AccessError, ValidationError) as error:
        code = getattr(error, "code", "data_import_rejected")
        raise CapabilityError(code) from None
    public = dict(result)
    public.pop("import_options", None)
    return public


def _request(context: CapabilityContext, arguments):
    _turn_bound(context)
    try:
        return context.env["odoo.ai.data.import.session"].validate_csv_request(
            turn_uuid=context.turn_id,
            attachment_id=arguments.get("attachment_id"),
            target_model=arguments.get("model"),
            mapping=arguments.get("mapping"),
            chunk_size=arguments.get("chunk_size", _DEFAULT_CHUNK_SIZE),
        )
    except (DataImportWorkflowError, AccessError, ValidationError) as error:
        code = getattr(error, "code", "data_import_rejected")
        raise CapabilityError(code) from None


def _start_preview(context: CapabilityContext, arguments):
    request = _request(context, arguments)
    return CapabilityPreview(
        summary={
            "operation": "data_import_start_csv",
            "attachment_id": request["attachment_id"],
            "filename": request["filename"],
            "target_model": request["target_model"],
            "mapping": request["mapping"],
            "total_rows": request["total_rows"],
            "duplicate_rows": request["duplicate_rows"],
            "chunk_size": request["chunk_size"],
            "mapping_fingerprint": request["mapping_fingerprint"],
            "execution": "durable_background_chunks",
            "partial_failure_semantics": "whole_invalid_chunk_rejected",
        },
        precondition_fingerprint=request["request_fingerprint"],
    )


def _start_verify(context: CapabilityContext, arguments):
    result = context.metadata.get("capability_result")
    if not isinstance(result, dict):
        raise CapabilityError("capability_verification_invalid")
    session_uuid = result.get("session_uuid")
    try:
        status = context.env["odoo.ai.data.import.session"].status_for_current_user(
            session_uuid,
            recent_chunks=1,
        )
    except (DataImportWorkflowError, AccessError, ValidationError):
        return CapabilityVerification(
            verified=False,
            summary={"session_uuid": session_uuid if isinstance(session_uuid, str) else ""},
        )
    request = _request(context, arguments)
    verified = bool(
        status["target_model"] == request["target_model"]
        and status["mapping_fingerprint"] == request["mapping_fingerprint"]
        and status["total_rows"] == request["total_rows"]
        and status["state"] in {"queued", "running", "completed", "partial", "failed"}
    )
    return CapabilityVerification(
        verified=verified,
        summary={
            "session_uuid": status["session_uuid"],
            "state": status["state"],
            "total_rows": status["total_rows"],
        },
    )


@tool(
    name="assistant.data_import.inspect_csv",
    title="Inspect an attached CSV for import",
    description=(
        "Inspect a CSV attached to the CURRENT Assistant turn against one eligible Odoo "
        "business model. Returns bounded headers/examples, effective-user writable scalar "
        "fields and Odoo-native mapping suggestions. This never imports data and never "
        "expands model/field authority. Use the returned column_index and safe field names "
        "when proposing a final mapping."
    ),
    input_schema=_INSPECT_INPUT,
    output_schema=_INSPECT_OUTPUT,
    risk=CapabilityRisk.READ,
    effect=CapabilityEffect.READ_ONLY,
    tags=("assistant", "artifact", "csv", "import", "inspect"),
    max_calls=8,
    timeout_seconds=20,
    max_input_bytes=8 * 1024,
    max_output_bytes=192 * 1024,
)
def inspect_csv(context: CapabilityContext, arguments):
    return _inspect(context, arguments)


@tool(
    name="assistant.data_import.start_csv",
    title="Start a durable CSV import",
    description=(
        "Queue a validated CSV attached to the CURRENT turn for durable create-only import "
        "into one eligible Odoo business model. First call assistant.data_import.inspect_csv "
        "and use an explicit column_index-to-field mapping. The host revalidates the exact "
        "artifact, target ACL, mapping and row count, previews the request, applies policy/"
        "approval, then background workers dry-run and execute one bounded ORM chunk per "
        "transaction. Completed chunks have durable receipts and are not blindly replayed."
    ),
    input_schema=_START_INPUT,
    output_schema=_START_OUTPUT,
    risk=CapabilityRisk.ACTION,
    effect=CapabilityEffect.INTERNAL_IRREVERSIBLE,
    exposure=CapabilityExposure.PLAN,
    approval=CapabilityApproval.POLICY,
    tags=("assistant", "artifact", "csv", "import", "action", "create"),
    preview=_start_preview,
    verify=_start_verify,
    audit_metadata={
        "recovery_mode": "segmented",
        "journal_classification": "irreversible",
    },
    max_calls=2,
    timeout_seconds=30,
    max_input_bytes=32 * 1024,
    max_output_bytes=16 * 1024,
)
def start_csv(context: CapabilityContext, arguments):
    _request(context, arguments)
    try:
        session = context.env["odoo.ai.data.import.session"].create_csv_session(
            turn_uuid=context.turn_id,
            attachment_id=arguments.get("attachment_id"),
            target_model=arguments.get("model"),
            mapping=arguments.get("mapping"),
            chunk_size=arguments.get("chunk_size", _DEFAULT_CHUNK_SIZE),
        )
    except (DataImportWorkflowError, AccessError, ValidationError, UserError) as error:
        code = getattr(error, "code", "data_import_rejected")
        raise CapabilityError(code) from None
    return {
        "session_uuid": session.session_uuid,
        "state": session.state,
        "target_model": session.target_model,
        "filename": session.filename,
        "total_rows": session.total_rows,
        "duplicate_rows": session.duplicate_rows,
        "chunk_size": session.chunk_size,
        "mapping_fingerprint": session.mapping_fingerprint,
    }


@tool(
    name="assistant.data_import.status",
    title="Read durable import progress",
    description=(
        "Read one owned durable CSV import session by session_uuid. Returns exact imported, "
        "rejected and remaining row counts plus bounded recent chunk receipts. Use this for "
        "follow-ups after the background import was queued or interrupted."
    ),
    input_schema=_STATUS_INPUT,
    output_schema=_STATUS_OUTPUT,
    risk=CapabilityRisk.READ,
    effect=CapabilityEffect.READ_ONLY,
    tags=("assistant", "artifact", "csv", "import", "status", "receipt"),
    max_calls=12,
    timeout_seconds=10,
    max_input_bytes=4 * 1024,
    max_output_bytes=192 * 1024,
)
def import_status(context: CapabilityContext, arguments):
    _turn_bound(context)
    try:
        return context.env["odoo.ai.data.import.session"].status_for_current_user(
            arguments.get("session_uuid"),
            recent_chunks=arguments.get("recent_chunks", 8),
        )
    except (DataImportWorkflowError, AccessError, ValidationError) as error:
        code = getattr(error, "code", "data_import_rejected")
        raise CapabilityError(code) from None


__all__ = ["import_status", "inspect_csv", "start_csv"]
