"""Generic tabular aliases for CSV/XLS/XLSX/ODS imports.

The original P11 capability ids contain ``csv`` for compatibility.  These aliases give
the reasoning model an accurate format-neutral surface while reusing exactly the same
host validation, plan, policy, staging and receipt machinery.
"""

from __future__ import annotations

from odoo.exceptions import AccessError, ValidationError

from ....models.data_import import DataImportWorkflowError
from ..contracts import (
    CapabilityApproval,
    CapabilityContext,
    CapabilityEffect,
    CapabilityError,
    CapabilityExposure,
    CapabilityRisk,
)
from ..decorators import tool
from .assistant_data_import import (
    _DEFAULT_CHUNK_SIZE,
    _INSPECT_INPUT,
    _INSPECT_OUTPUT,
    _START_INPUT,
    _START_OUTPUT,
    _inspect,
    _start_preview,
    _start_verify,
    _turn_bound,
)


@tool(
    name="assistant.data_import.inspect_file",
    title="Inspect an attached CSV or spreadsheet for import",
    description=(
        "Inspect a CSV, XLS, XLSX or ODS file attached to the CURRENT Assistant turn "
        "against one eligible Odoo business model. Returns bounded headers/examples, "
        "effective-user writable scalar fields and Odoo-native mapping suggestions. "
        "This never imports data and never expands model/field authority."
    ),
    input_schema=_INSPECT_INPUT,
    output_schema=_INSPECT_OUTPUT,
    risk=CapabilityRisk.READ,
    effect=CapabilityEffect.READ_ONLY,
    tags=("assistant", "artifact", "spreadsheet", "csv", "import", "inspect"),
    max_calls=8,
    timeout_seconds=20,
    max_input_bytes=8 * 1024,
    max_output_bytes=192 * 1024,
)
def inspect_file(context: CapabilityContext, arguments):
    return _inspect(context, arguments)


@tool(
    name="assistant.data_import.start_file",
    title="Start a durable CSV or spreadsheet import",
    description=(
        "Queue a validated CSV, XLS, XLSX or ODS attachment from the CURRENT turn for "
        "durable create-only import into one eligible Odoo business model. First call "
        "assistant.data_import.inspect_file and provide an explicit column_index-to-field "
        "mapping. The host revalidates the exact artifact, stages normalized rows once, "
        "applies policy/approval and imports bounded canonical chunks with durable receipts."
    ),
    input_schema=_START_INPUT,
    output_schema=_START_OUTPUT,
    risk=CapabilityRisk.ACTION,
    effect=CapabilityEffect.INTERNAL_IRREVERSIBLE,
    exposure=CapabilityExposure.PLAN,
    approval=CapabilityApproval.POLICY,
    tags=("assistant", "artifact", "spreadsheet", "csv", "import", "action", "create"),
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
def start_file(context: CapabilityContext, arguments):
    _turn_bound(context)
    try:
        session = context.env["odoo.ai.data.import.session"].create_csv_session(
            turn_uuid=context.turn_id,
            attachment_id=arguments.get("attachment_id"),
            target_model=arguments.get("model"),
            mapping=arguments.get("mapping"),
            chunk_size=arguments.get("chunk_size", _DEFAULT_CHUNK_SIZE),
        )
    except (DataImportWorkflowError, AccessError, ValidationError) as error:
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
        "planned_chunk_count": session.planned_chunk_count,
        "mapping_fingerprint": session.mapping_fingerprint,
    }


__all__ = ["inspect_file", "start_file"]
