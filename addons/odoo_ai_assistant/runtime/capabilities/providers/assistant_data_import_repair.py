"""Phase 11 deterministic cleanup and repair capabilities for durable imports."""

from __future__ import annotations

from odoo.exceptions import AccessError, UserError, ValidationError

from ....models.data_import import DataImportWorkflowError
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
from .assistant_data_import import _turn_bound

_DEFAULT_CHUNK_SIZE = 250
_MAX_MAPPING_ITEMS = 64
_MAX_CLEANUP_RULES = 32
_MAX_REPAIR_CORRECTIONS = 64

_MAPPING_ITEM = {
    "type": "object",
    "properties": {
        "column_index": {"type": "integer", "minimum": 0, "maximum": 63},
        "field": {"type": "string", "minLength": 1, "maxLength": 128},
    },
    "required": ["column_index", "field"],
    "additionalProperties": False,
}
_CLEANUP_RULE = {
    "type": "object",
    "properties": {
        "field": {"type": "string", "minLength": 1, "maxLength": 128},
        "operation": {
            "type": "string",
            "enum": [
                "trim",
                "normalize_whitespace",
                "replace_exact",
                "set_if_empty",
            ],
        },
        "match": {"type": "string", "maxLength": 1024},
        "value": {"type": "string", "maxLength": 1024},
    },
    "required": ["field", "operation"],
    "additionalProperties": False,
}
_CHANGE_SAMPLE = {
    "type": "object",
    "properties": {
        "row": {"type": "integer", "minimum": 1},
        "field": {"type": "string"},
        "before": {"type": "string"},
        "after": {"type": "string"},
    },
    "required": ["row", "field", "before", "after"],
    "additionalProperties": False,
}
_CLEANUP_INPUT = {
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
        "cleanup_rules": {
            "type": "array",
            "minItems": 1,
            "maxItems": _MAX_CLEANUP_RULES,
            "items": _CLEANUP_RULE,
        },
        "chunk_size": {
            "type": "integer",
            "minimum": 1,
            "maximum": 1000,
            "default": _DEFAULT_CHUNK_SIZE,
        },
    },
    "required": ["attachment_id", "model", "mapping", "cleanup_rules"],
    "additionalProperties": False,
}
_CLEANUP_INSPECT_OUTPUT = {
    "type": "object",
    "properties": {
        "attachment_id": {"type": "integer"},
        "filename": {"type": "string"},
        "target_model": {"type": "string"},
        "total_rows": {"type": "integer"},
        "duplicate_rows_before": {"type": "integer"},
        "duplicate_rows_after": {"type": "integer"},
        "planned_corrected_rows": {"type": "integer"},
        "cleanup_rules": {
            "type": "array",
            "maxItems": _MAX_CLEANUP_RULES,
            "items": _CLEANUP_RULE,
        },
        "samples": {
            "type": "array",
            "maxItems": 12,
            "items": _CHANGE_SAMPLE,
        },
        "cleanup_fingerprint": {"type": "string"},
        "mapping_fingerprint": {"type": "string"},
        "chunk_size": {"type": "integer"},
        "planned_chunk_count": {"type": "integer"},
    },
    "required": [
        "attachment_id",
        "filename",
        "target_model",
        "total_rows",
        "duplicate_rows_before",
        "duplicate_rows_after",
        "planned_corrected_rows",
        "cleanup_rules",
        "samples",
        "cleanup_fingerprint",
        "mapping_fingerprint",
        "chunk_size",
        "planned_chunk_count",
    ],
    "additionalProperties": False,
}
_CLEANUP_START_OUTPUT = {
    "type": "object",
    "properties": {
        "session_uuid": {"type": "string"},
        "state": {"type": "string"},
        "target_model": {"type": "string"},
        "filename": {"type": "string"},
        "total_rows": {"type": "integer"},
        "duplicate_rows": {"type": "integer"},
        "chunk_size": {"type": "integer"},
        "planned_chunk_count": {"type": "integer"},
        "mapping_fingerprint": {"type": "string"},
        "cleanup_fingerprint": {"type": "string"},
        "planned_corrected_rows": {"type": "integer"},
    },
    "required": [
        "session_uuid",
        "state",
        "target_model",
        "filename",
        "total_rows",
        "duplicate_rows",
        "chunk_size",
        "planned_chunk_count",
        "mapping_fingerprint",
        "cleanup_fingerprint",
        "planned_corrected_rows",
    ],
    "additionalProperties": False,
}
_MESSAGE = {
    "type": "object",
    "properties": {
        "type": {"type": "string"},
        "message": {"type": "string"},
    },
    "required": ["type", "message"],
    "additionalProperties": False,
}
_REJECTED_ROW = {
    "type": "object",
    "properties": {
        "row": {"type": "integer", "minimum": 1},
        "values": {
            "type": "object",
            "additionalProperties": {"type": "string"},
        },
    },
    "required": ["row", "values"],
    "additionalProperties": False,
}
_REJECTED_INPUT = {
    "type": "object",
    "properties": {
        "session_uuid": {"type": "string", "minLength": 32, "maxLength": 32},
        "max_rows": {"type": "integer", "minimum": 1, "maximum": 20, "default": 8},
    },
    "required": ["session_uuid"],
    "additionalProperties": False,
}
_REJECTED_OUTPUT = {
    "type": "object",
    "properties": {
        "session_uuid": {"type": "string"},
        "state": {"type": "string"},
        "target_model": {"type": "string"},
        "rejected_sequence": {"type": "integer"},
        "row_start": {"type": "integer"},
        "row_end": {"type": "integer"},
        "messages": {"type": "array", "maxItems": 8, "items": _MESSAGE},
        "rows": {"type": "array", "maxItems": 20, "items": _REJECTED_ROW},
        "repair_revision": {"type": "integer"},
        "mapping_fingerprint": {"type": "string"},
        "prepared_rows_fingerprint": {"type": "string"},
    },
    "required": [
        "session_uuid",
        "state",
        "target_model",
        "rejected_sequence",
        "row_start",
        "row_end",
        "messages",
        "rows",
        "repair_revision",
        "mapping_fingerprint",
        "prepared_rows_fingerprint",
    ],
    "additionalProperties": False,
}
_CORRECTION = {
    "type": "object",
    "properties": {
        "row": {"type": "integer", "minimum": 1},
        "field": {"type": "string", "minLength": 1, "maxLength": 128},
        "value": {"type": "string", "maxLength": 1024},
    },
    "required": ["row", "field", "value"],
    "additionalProperties": False,
}
_REPAIR_INPUT = {
    "type": "object",
    "properties": {
        "session_uuid": {"type": "string", "minLength": 32, "maxLength": 32},
        "corrections": {
            "type": "array",
            "minItems": 1,
            "maxItems": _MAX_REPAIR_CORRECTIONS,
            "items": _CORRECTION,
        },
    },
    "required": ["session_uuid", "corrections"],
    "additionalProperties": False,
}
_REPAIR_OUTPUT = {
    "type": "object",
    "properties": {
        "session_uuid": {"type": "string"},
        "state": {"type": "string"},
        "target_model": {"type": "string"},
        "repair_revision": {"type": "integer"},
        "repair_fingerprint": {"type": "string"},
        "rejected_sequence": {"type": "integer"},
        "planned_corrected_rows": {"type": "integer"},
        "planned_chunk_count": {"type": "integer"},
        "prepared_rows_fingerprint": {"type": "string"},
    },
    "required": [
        "session_uuid",
        "state",
        "target_model",
        "repair_revision",
        "repair_fingerprint",
        "rejected_sequence",
        "planned_corrected_rows",
        "planned_chunk_count",
        "prepared_rows_fingerprint",
    ],
    "additionalProperties": False,
}


def _workflow_error(error):
    code = getattr(error, "code", "data_import_rejected")
    raise CapabilityError(code) from None


def _cleanup_request(context: CapabilityContext, arguments):
    _turn_bound(context)
    try:
        return context.env["odoo.ai.data.import.session"]._prepare_cleanup_request(
            turn_uuid=context.turn_id,
            attachment_id=arguments.get("attachment_id"),
            target_model=arguments.get("model"),
            mapping=arguments.get("mapping"),
            cleanup_rules=arguments.get("cleanup_rules"),
            chunk_size=arguments.get("chunk_size", _DEFAULT_CHUNK_SIZE),
        )
    except (DataImportWorkflowError, AccessError, ValidationError, UserError) as error:
        _workflow_error(error)


def _cleanup_public(request):
    return {
        "attachment_id": request["attachment_id"],
        "filename": request["filename"],
        "target_model": request["target_model"],
        "total_rows": request["total_rows"],
        "duplicate_rows_before": request["duplicate_rows_before"],
        "duplicate_rows_after": request["duplicate_rows"],
        "planned_corrected_rows": request["planned_corrected_rows"],
        "cleanup_rules": request["cleanup_rules"],
        "samples": request["cleanup_samples"],
        "cleanup_fingerprint": request["cleanup_fingerprint"],
        "mapping_fingerprint": request["mapping_fingerprint"],
        "chunk_size": request["chunk_size"],
        "planned_chunk_count": request["planned_chunks"],
    }


def _cleanup_preview(context: CapabilityContext, arguments):
    request = _cleanup_request(context, arguments)
    public = _cleanup_public(request)
    return CapabilityPreview(
        summary={
            "operation": "data_import_start_clean_csv",
            **public,
            "execution": "durable_background_chunks",
            "cleanup_semantics": "deterministic_host_bounded_rules",
        },
        precondition_fingerprint=request["request_fingerprint"],
    )


def _cleanup_verify(context: CapabilityContext, arguments):
    del arguments
    result = context.metadata.get("capability_result")
    if not isinstance(result, dict):
        raise CapabilityError("capability_verification_invalid")
    try:
        status = context.env["odoo.ai.data.import.session"].status_for_current_user(
            result.get("session_uuid"),
            recent_chunks=1,
        )
        metadata = context.env[
            "odoo.ai.data.import.session"
        ].cleanup_metadata_for_current_user(result.get("session_uuid"))
    except (DataImportWorkflowError, AccessError, ValidationError, UserError):
        return CapabilityVerification(
            verified=False,
            summary={"session_uuid": str(result.get("session_uuid") or "")},
        )
    verified = bool(
        status["target_model"] == result.get("target_model")
        and status["total_rows"] == result.get("total_rows")
        and status["planned_chunk_count"] == result.get("planned_chunk_count")
        and metadata["cleanup_fingerprint"] == result.get("cleanup_fingerprint")
        and metadata["planned_corrected_rows"] == result.get("planned_corrected_rows")
        and status["state"] in {"queued", "running", "completed", "partial", "failed"}
    )
    return CapabilityVerification(
        verified=verified,
        summary={
            "session_uuid": status["session_uuid"],
            "state": status["state"],
            "planned_corrected_rows": metadata["planned_corrected_rows"],
        },
    )


def _repair_request(context: CapabilityContext, arguments):
    _turn_bound(context)
    try:
        return context.env["odoo.ai.data.import.session"]._prepare_repair_request(
            session_uuid=arguments.get("session_uuid"),
            corrections=arguments.get("corrections"),
        )
    except (DataImportWorkflowError, AccessError, ValidationError, UserError) as error:
        _workflow_error(error)


def _repair_public(plan):
    return {
        "session_uuid": plan["session_uuid"],
        "target_model": plan["target_model"],
        "rejected_sequence": plan["rejected_sequence"],
        "row_start": plan["row_start"],
        "row_end": plan["row_end"],
        "repair_revision": plan["repair_revision"],
        "repair_fingerprint": plan["repair_fingerprint"],
        "corrections": plan["corrections"],
        "corrected_rows_planned": plan["corrected_rows_planned"],
        "planned_corrected_rows": plan["planned_corrected_rows"],
        "remaining_rows": plan["remaining_rows"],
        "planned_chunk_count": plan["planned_chunk_count"],
        "prepared_rows_fingerprint": plan["prepared_rows_fingerprint"],
    }


def _repair_preview(context: CapabilityContext, arguments):
    plan = _repair_request(context, arguments)
    return CapabilityPreview(
        summary={
            "operation": "data_import_resume_csv",
            **_repair_public(plan),
            "resume_semantics": "retry_rejected_window_without_replaying_completed_chunks",
        },
        precondition_fingerprint=plan["repair_fingerprint"],
    )


def _repair_verify(context: CapabilityContext, arguments):
    del arguments
    result = context.metadata.get("capability_result")
    if not isinstance(result, dict):
        raise CapabilityError("capability_verification_invalid")
    try:
        metadata = context.env[
            "odoo.ai.data.import.session"
        ].repair_metadata_for_current_user(result.get("session_uuid"))
    except (DataImportWorkflowError, AccessError, ValidationError, UserError):
        return CapabilityVerification(
            verified=False,
            summary={"session_uuid": str(result.get("session_uuid") or "")},
        )
    verified = bool(
        metadata["repair_revision"] == result.get("repair_revision")
        and metadata["last_repair_fingerprint"] == result.get("repair_fingerprint")
        and metadata["prepared_rows_fingerprint"]
        == result.get("prepared_rows_fingerprint")
        and metadata["planned_chunk_count"] == result.get("planned_chunk_count")
        and metadata["state"] in {"queued", "running", "completed", "partial", "failed"}
    )
    return CapabilityVerification(
        verified=verified,
        summary={
            "session_uuid": metadata["session_uuid"],
            "state": metadata["state"],
            "repair_revision": metadata["repair_revision"],
        },
    )


@tool(
    name="assistant.data_import.inspect_cleanup",
    title="Preview deterministic CSV cleanup",
    description=(
        "Apply a bounded deterministic cleanup proposal to the mapped rows of a current-turn "
        "CSV without importing anything. Rules may trim or normalize mapped text, replace an "
        "exact mapped value, or fill an empty mapped value. Returns exact changed-row counts, "
        "duplicate counts and bounded before/after samples. Cleanup never widens the approved "
        "model or field mapping."
    ),
    input_schema=_CLEANUP_INPUT,
    output_schema=_CLEANUP_INSPECT_OUTPUT,
    risk=CapabilityRisk.READ,
    effect=CapabilityEffect.READ_ONLY,
    tags=("assistant", "artifact", "csv", "import", "cleanup", "inspect"),
    max_calls=8,
    timeout_seconds=30,
    max_input_bytes=48 * 1024,
    max_output_bytes=64 * 1024,
)
def inspect_cleanup(context: CapabilityContext, arguments):
    return _cleanup_public(_cleanup_request(context, arguments))


@tool(
    name="assistant.data_import.start_clean_csv",
    title="Start a cleaned durable CSV import",
    description=(
        "Queue a create-only CSV import after applying explicitly proposed deterministic cleanup "
        "rules to already mapped safe fields. The host previews exact changes and fingerprints, "
        "policy/approval still applies, and corrected_rows increases only for changed rows that "
        "actually commit successfully."
    ),
    input_schema=_CLEANUP_INPUT,
    output_schema=_CLEANUP_START_OUTPUT,
    risk=CapabilityRisk.ACTION,
    effect=CapabilityEffect.INTERNAL_IRREVERSIBLE,
    exposure=CapabilityExposure.PLAN,
    approval=CapabilityApproval.POLICY,
    tags=("assistant", "artifact", "csv", "import", "cleanup", "action"),
    preview=_cleanup_preview,
    verify=_cleanup_verify,
    audit_metadata={
        "recovery_mode": "segmented",
        "journal_classification": "irreversible",
    },
    max_calls=2,
    timeout_seconds=30,
    max_input_bytes=48 * 1024,
    max_output_bytes=16 * 1024,
)
def start_clean_csv(context: CapabilityContext, arguments):
    _turn_bound(context)
    try:
        session = context.env["odoo.ai.data.import.session"].create_clean_csv_session(
            turn_uuid=context.turn_id,
            attachment_id=arguments.get("attachment_id"),
            target_model=arguments.get("model"),
            mapping=arguments.get("mapping"),
            cleanup_rules=arguments.get("cleanup_rules"),
            chunk_size=arguments.get("chunk_size", _DEFAULT_CHUNK_SIZE),
        )
        metadata = context.env[
            "odoo.ai.data.import.session"
        ].cleanup_metadata_for_current_user(session.session_uuid)
    except (DataImportWorkflowError, AccessError, ValidationError, UserError) as error:
        _workflow_error(error)
    return {
        "session_uuid": session.session_uuid,
        "state": session.state,
        "target_model": session.target_model,
        "filename": session.filename,
        "total_rows": session.total_rows,
        "duplicate_rows": session.duplicate_rows,
        "chunk_size": session.chunk_size,
        "planned_chunk_count": session.planned_chunk_count,
        "mapping_fingerprint": session.mapping_fingerprint,
        "cleanup_fingerprint": metadata["cleanup_fingerprint"],
        "planned_corrected_rows": metadata["planned_corrected_rows"],
    }


@tool(
    name="assistant.data_import.inspect_rejected",
    title="Inspect a rejected import chunk",
    description=(
        "Read the bounded row window and sanitized Odoo validation messages for the latest "
        "rejected chunk of an owned durable import session. Values are exposed only for fields "
        "already present in the approved mapping so the model can propose explicit corrections."
    ),
    input_schema=_REJECTED_INPUT,
    output_schema=_REJECTED_OUTPUT,
    risk=CapabilityRisk.READ,
    effect=CapabilityEffect.READ_ONLY,
    tags=("assistant", "artifact", "csv", "import", "repair", "inspect"),
    max_calls=8,
    timeout_seconds=10,
    max_input_bytes=4 * 1024,
    max_output_bytes=96 * 1024,
)
def inspect_rejected(context: CapabilityContext, arguments):
    _turn_bound(context)
    try:
        return context.env[
            "odoo.ai.data.import.session"
        ].inspect_rejected_for_current_user(
            arguments.get("session_uuid"),
            max_rows=arguments.get("max_rows", 8),
        )
    except (DataImportWorkflowError, AccessError, ValidationError, UserError) as error:
        _workflow_error(error)


@tool(
    name="assistant.data_import.resume_csv",
    title="Repair and resume a rejected CSV import",
    description=(
        "Apply explicit bounded corrections only to the current rejected mapped-row window and "
        "resume the same durable import from its committed cursor. Previously completed chunks "
        "are retained and never replayed. The rejected receipt remains historical evidence and "
        "a new repair fingerprint binds the retry."
    ),
    input_schema=_REPAIR_INPUT,
    output_schema=_REPAIR_OUTPUT,
    risk=CapabilityRisk.ACTION,
    effect=CapabilityEffect.INTERNAL_IRREVERSIBLE,
    exposure=CapabilityExposure.PLAN,
    approval=CapabilityApproval.POLICY,
    tags=("assistant", "artifact", "csv", "import", "repair", "resume", "action"),
    preview=_repair_preview,
    verify=_repair_verify,
    audit_metadata={
        "recovery_mode": "segmented",
        "journal_classification": "irreversible",
    },
    max_calls=4,
    timeout_seconds=20,
    max_input_bytes=48 * 1024,
    max_output_bytes=16 * 1024,
)
def resume_csv(context: CapabilityContext, arguments):
    _turn_bound(context)
    plan = _repair_request(context, arguments)
    try:
        session = context.env["odoo.ai.data.import.session"].resume_with_corrections(
            session_uuid=arguments.get("session_uuid"),
            corrections=arguments.get("corrections"),
        )
        metadata = context.env[
            "odoo.ai.data.import.session"
        ].repair_metadata_for_current_user(session.session_uuid)
    except (DataImportWorkflowError, AccessError, ValidationError, UserError) as error:
        _workflow_error(error)
    return {
        "session_uuid": session.session_uuid,
        "state": session.state,
        "target_model": session.target_model,
        "repair_revision": metadata["repair_revision"],
        "repair_fingerprint": metadata["last_repair_fingerprint"],
        "rejected_sequence": plan["rejected_sequence"],
        "planned_corrected_rows": metadata["planned_corrected_rows"],
        "planned_chunk_count": metadata["planned_chunk_count"],
        "prepared_rows_fingerprint": metadata["prepared_rows_fingerprint"],
    }


__all__ = [
    "inspect_cleanup",
    "inspect_rejected",
    "resume_csv",
    "start_clean_csv",
]
