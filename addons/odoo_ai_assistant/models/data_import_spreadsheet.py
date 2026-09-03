"""Spreadsheet breadth for the accepted P11 durable import pipeline.

Odoo 18 base_import natively understands CSV, XLS, XLSX and ODS. The accepted P11
workflow initially hard-coded CSV at its attachment and base_import seams. This model
extension keeps the same staged-row/chunk/receipt semantics while allowing those
native spreadsheet formats at preparation time. Execution still uses canonical CSV
chunks after rows are staged, so recovery behavior is unchanged.
"""

from __future__ import annotations

import math

from odoo import SUPERUSER_ID, api, fields, models
from odoo.exceptions import AccessError

from .data_import import (
    _DEFAULT_CHUNK_SIZE,
    _MAX_CHUNKS_PER_SESSION,
    _MAX_COLUMNS,
    DataImportWorkflowError,
    _attachment_bytes,
    _chunk_size,
    _column_examples,
    _duplicate_rows,
    _estimated_rows,
    _fields_vector,
    _fingerprint,
    _headers,
    _import_fields,
    _normalized_mapping,
    _prepared_rows_fingerprint,
    _safe_import_fields,
    _safe_import_options,
    _target_model,
    _validate_prepared_rows,
)

_IMPORT_MIMETYPE_BY_EXTENSION = {
    ".csv": "text/csv",
    ".xls": "application/vnd.ms-excel",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".ods": "application/vnd.oasis.opendocument.spreadsheet",
}


class AssistantDataImportSpreadsheet(models.Model):
    _inherit = "odoo.ai.data.import.session"

    @api.model
    def inspect_csv_attachment(
        self,
        *,
        turn_uuid,
        attachment_id,
        target_model,
    ):
        """Inspect one current-turn native tabular file under effective-user authority."""

        if self.env.su:
            raise AccessError("Assistant import inspection requires the effective user")
        attachment = _bound_tabular_attachment(
            self.env,
            turn_uuid=turn_uuid,
            attachment_id=attachment_id,
        )
        target_model = _target_model(self.env, target_model)
        safe_fields = _safe_import_fields(self.env, target_model)
        raw = _attachment_bytes(attachment)
        preview = _native_tabular_preview(
            self.env,
            raw=raw,
            filename=attachment.filename,
            target_model=target_model,
        )
        headers = _headers(preview)
        if len(headers) > _MAX_COLUMNS:
            raise DataImportWorkflowError("data_import_too_many_columns")
        safe_by_name = {item["name"]: item for item in safe_fields}
        native_matches = preview.get("matches")
        suggestions = []
        if isinstance(native_matches, dict):
            for index, path in native_matches.items():
                if (
                    type(index) is int
                    and 0 <= index < len(headers)
                    and isinstance(path, list)
                    and len(path) == 1
                    and isinstance(path[0], str)
                    and path[0] in safe_by_name
                ):
                    suggestions.append(
                        {
                            "column_index": index,
                            "column": headers[index],
                            "field": path[0],
                        }
                    )
        return {
            "attachment_id": attachment.id,
            "filename": attachment.filename,
            "mimetype": attachment.mimetype,
            "size": attachment.file_size,
            "fingerprint": f"sha256:{attachment.fingerprint}",
            "target_model": target_model,
            "headers": headers,
            "columns": _column_examples(preview.get("preview"), headers),
            "safe_fields": safe_fields,
            "suggested_mapping": sorted(
                suggestions,
                key=lambda item: item["column_index"],
            ),
            "estimated_rows": _estimated_rows(preview),
            "import_options": _safe_import_options(preview.get("options")),
        }

    @api.model
    def _prepare_csv_request(
        self,
        *,
        turn_uuid,
        attachment_id,
        target_model,
        mapping,
        chunk_size=_DEFAULT_CHUNK_SIZE,
    ):
        """Prepare CSV/XLS/XLSX/ODS into the same immutable staged-row contract."""

        inspection = self.inspect_csv_attachment(
            turn_uuid=turn_uuid,
            attachment_id=attachment_id,
            target_model=target_model,
        )
        chunk_size = _chunk_size(chunk_size)
        normalized_mapping = _normalized_mapping(
            mapping,
            headers=inspection["headers"],
            safe_fields=inspection["safe_fields"],
        )
        fields_vector = _fields_vector(inspection["headers"], normalized_mapping)
        attachment = _bound_tabular_attachment(
            self.env,
            turn_uuid=turn_uuid,
            attachment_id=attachment_id,
        )
        raw = _attachment_bytes(attachment)
        exact_rows, import_fields = _mapped_tabular_rows(
            self.env,
            raw=raw,
            filename=attachment.filename,
            target_model=inspection["target_model"],
            fields_vector=fields_vector,
            options=inspection["import_options"],
        )
        total_rows = len(exact_rows)
        if total_rows <= 0:
            raise DataImportWorkflowError("data_import_no_rows")
        planned_chunks = math.ceil(total_rows / chunk_size)
        if planned_chunks > _MAX_CHUNKS_PER_SESSION:
            raise DataImportWorkflowError("data_import_too_many_chunks")
        prepared_rows_fingerprint = _prepared_rows_fingerprint(
            import_fields,
            exact_rows,
        )
        duplicate_rows = _duplicate_rows(exact_rows)
        mapping_fingerprint = _fingerprint(
            {
                "model": inspection["target_model"],
                "headers": inspection["headers"],
                "mapping": normalized_mapping,
            }
        )
        request_fingerprint = _fingerprint(
            {
                "attachment": inspection["fingerprint"],
                "model": inspection["target_model"],
                "mapping": normalized_mapping,
                "options": inspection["import_options"],
                "chunk_size": chunk_size,
                "prepared_rows": prepared_rows_fingerprint,
            }
        )
        return {
            **inspection,
            "mapping": normalized_mapping,
            "import_fields": import_fields,
            "prepared_rows": exact_rows,
            "prepared_rows_fingerprint": prepared_rows_fingerprint,
            "chunk_size": chunk_size,
            "planned_chunks": planned_chunks,
            "total_rows": total_rows,
            "duplicate_rows": duplicate_rows,
            "mapping_fingerprint": mapping_fingerprint,
            "request_fingerprint": request_fingerprint,
        }

    @api.model
    def create_csv_session(
        self,
        *,
        turn_uuid,
        attachment_id,
        target_model,
        mapping,
        chunk_size=_DEFAULT_CHUNK_SIZE,
    ):
        """Persist the generalized native-tabular request using the accepted P11 session."""

        if self.env.su:
            raise AccessError("Assistant import creation requires the effective user")
        request = self._prepare_csv_request(
            turn_uuid=turn_uuid,
            attachment_id=attachment_id,
            target_model=target_model,
            mapping=mapping,
            chunk_size=chunk_size,
        )
        attachment = _bound_tabular_attachment(
            self.env,
            turn_uuid=turn_uuid,
            attachment_id=attachment_id,
        )
        turn = attachment.turn_id
        system_model = self.with_user(SUPERUSER_ID)
        existing = system_model.search(
            [
                ("turn_id", "=", turn.id),
                ("request_fingerprint", "=", request["request_fingerprint"]),
            ],
            limit=1,
        )
        if existing:
            return existing

        session = system_model.create(
            {
                "owner_user_id": self.env.uid,
                "company_id": self.env.company.id,
                "turn_id": turn.id,
                "conversation_id": attachment.conversation_id.id or False,
                "source_attachment_id": attachment.id,
                "filename": attachment.filename,
                "mimetype": attachment.mimetype,
                "file_data": attachment.data,
                "file_size": attachment.file_size,
                "file_fingerprint": attachment.fingerprint,
                "target_model": request["target_model"],
                "headers_json": request["headers"],
                "mapping_json": request["mapping"],
                "import_fields_json": request["import_fields"],
                "prepared_rows_json": request["prepared_rows"],
                "prepared_rows_fingerprint": request["prepared_rows_fingerprint"],
                "import_options_json": request["import_options"],
                "request_fingerprint": request["request_fingerprint"],
                "mapping_fingerprint": request["mapping_fingerprint"],
                "chunk_size": request["chunk_size"],
                "planned_chunk_count": request["planned_chunks"],
                "total_rows": request["total_rows"],
                "duplicate_rows": request["duplicate_rows"],
                "state": "queued",
            }
        )
        session._trigger_processing_cron()
        return session


def _extension(filename: str) -> str:
    position = filename.rfind(".")
    return filename[position:].casefold() if position >= 0 else ""


def _bound_tabular_attachment(env, *, turn_uuid, attachment_id):
    if (
        not isinstance(turn_uuid, str)
        or not turn_uuid
        or type(attachment_id) is not int
        or attachment_id <= 0
    ):
        raise DataImportWorkflowError("data_import_attachment_invalid")
    attachment = env["odoo.ai.knowledge.attachment"].search(
        [
            ("id", "=", attachment_id),
            ("user_id", "=", env.uid),
            ("company_id", "=", env.company.id),
            ("turn_id.turn_uuid", "=", turn_uuid),
        ],
        limit=1,
    )
    extension = _extension(attachment.filename) if attachment else ""
    expected_mimetype = _IMPORT_MIMETYPE_BY_EXTENSION.get(extension)
    if (
        not attachment
        or attachment.expires_at < fields.Datetime.now()
        or expected_mimetype is None
        or attachment.mimetype != expected_mimetype
    ):
        raise DataImportWorkflowError("data_import_attachment_invalid")
    return attachment


def _native_tabular_wizard(env, *, raw, filename, target_model):
    mimetype = _IMPORT_MIMETYPE_BY_EXTENSION.get(_extension(filename))
    if mimetype is None:
        raise DataImportWorkflowError("data_import_attachment_invalid")
    return env["base_import.import"].create(
        {
            "res_model": target_model,
            "file_name": filename,
            "file_type": mimetype,
            "file": raw,
        }
    )


def _native_tabular_preview(env, *, raw, filename, target_model):
    wizard = _native_tabular_wizard(
        env,
        raw=raw,
        filename=filename,
        target_model=target_model,
    )
    try:
        preview = wizard.parse_preview(
            {
                "has_headers": True,
                "separator": "",
                "quoting": '"',
            },
            count=10,
        )
    except Exception as error:
        raise DataImportWorkflowError("data_import_file_invalid") from error
    if not isinstance(preview, dict) or preview.get("error"):
        raise DataImportWorkflowError("data_import_file_invalid")
    return preview


def _mapped_tabular_rows(
    env,
    *,
    raw,
    filename,
    target_model,
    fields_vector,
    options,
):
    wizard = _native_tabular_wizard(
        env,
        raw=raw,
        filename=filename,
        target_model=target_model,
    )
    try:
        rows, import_fields = wizard._convert_import_data(
            fields_vector,
            dict(options),
        )
    except Exception as error:
        raise DataImportWorkflowError("data_import_file_invalid") from error
    if not isinstance(rows, list) or not isinstance(import_fields, list):
        raise DataImportWorkflowError("data_import_file_invalid")
    import_fields = _import_fields(import_fields)
    _validate_prepared_rows(rows, import_fields=import_fields)
    return rows, import_fields


__all__ = ["AssistantDataImportSpreadsheet"]
