"""Durable bounded CSV import sessions for Phase 11 artifact workflows."""

from __future__ import annotations

import base64
import hashlib
import json
from datetime import timedelta
from uuid import uuid4

from odoo import SUPERUSER_ID, api, fields, models
from odoo.exceptions import AccessError, MissingError, UserError, ValidationError

from ..services.turn_context import (
    TurnContextError,
    agent_model_is_eligible,
    visible_action_preview_fields,
)

_MAX_COLUMNS = 64
_MAX_COLUMN_NAME = 160
_MAX_SAMPLE_VALUES = 3
_MAX_SAMPLE_VALUE = 160
_DEFAULT_CHUNK_SIZE = 250
_MIN_CHUNK_SIZE = 1
_MAX_CHUNK_SIZE = 1_000
_MAX_RECENT_CHUNKS = 20
_MAX_PUBLIC_MESSAGES = 8
_MAX_PUBLIC_MESSAGE = 240
_RETENTION_DAYS = 30
_ALLOWED_FIELD_TYPES = frozenset(
    {
        "boolean",
        "char",
        "date",
        "datetime",
        "float",
        "integer",
        "monetary",
        "selection",
        "text",
    }
)
_TERMINAL_STATES = frozenset({"completed", "partial", "failed"})
_SAFE_OPTION_KEYS = (
    "encoding",
    "separator",
    "quoting",
    "date_format",
    "datetime_format",
    "float_thousand_separator",
    "float_decimal_separator",
)


class DataImportWorkflowError(RuntimeError):
    """Sanitized durable-import failure."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class DataImportChunkRejected(DataImportWorkflowError):
    """A bounded chunk failed Odoo's dry-run/real validation."""

    def __init__(
        self,
        *,
        sequence: int,
        row_start: int,
        row_end: int,
        input_count: int,
        messages,
    ) -> None:
        super().__init__("data_import_chunk_rejected")
        self.sequence = sequence
        self.row_start = row_start
        self.row_end = row_end
        self.input_count = input_count
        self.messages = _sanitize_messages(messages)


class AssistantDataImportSession(models.Model):
    _name = "odoo.ai.data.import.session"
    _description = "Odoo AI Assistant Data Import Session"
    _order = "id desc"

    session_uuid = fields.Char(
        required=True,
        readonly=True,
        index=True,
        default=lambda self: uuid4().hex,
        size=32,
    )
    owner_user_id = fields.Many2one(
        "res.users",
        required=True,
        readonly=True,
        index=True,
        ondelete="cascade",
    )
    company_id = fields.Many2one(
        "res.company",
        required=True,
        readonly=True,
        index=True,
        ondelete="cascade",
    )
    turn_id = fields.Many2one(
        "odoo.ai.turn",
        readonly=True,
        index=True,
        ondelete="set null",
    )
    conversation_id = fields.Many2one(
        "odoo.ai.conversation",
        readonly=True,
        index=True,
        ondelete="set null",
    )
    source_attachment_id = fields.Many2one(
        "odoo.ai.knowledge.attachment",
        readonly=True,
        index=True,
        ondelete="set null",
    )
    filename = fields.Char(required=True, readonly=True, size=255)
    mimetype = fields.Char(required=True, readonly=True, size=120)
    file_data = fields.Binary(required=True, readonly=True, attachment=True, copy=False)
    file_size = fields.Integer(required=True, readonly=True)
    file_fingerprint = fields.Char(required=True, readonly=True, index=True, size=64)
    target_model = fields.Char(required=True, readonly=True, index=True, size=128)
    headers_json = fields.Json(required=True, readonly=True, copy=False, default=list)
    mapping_json = fields.Json(required=True, readonly=True, copy=False, default=list)
    import_options_json = fields.Json(required=True, readonly=True, copy=False, default=dict)
    request_fingerprint = fields.Char(required=True, readonly=True, index=True, size=71)
    mapping_fingerprint = fields.Char(required=True, readonly=True, index=True, size=71)
    chunk_size = fields.Integer(required=True, readonly=True, default=_DEFAULT_CHUNK_SIZE)
    total_rows = fields.Integer(required=True, readonly=True, default=0)
    duplicate_rows = fields.Integer(required=True, readonly=True, default=0)
    next_row = fields.Integer(required=True, readonly=True, default=0)
    imported_rows = fields.Integer(required=True, readonly=True, default=0)
    failed_rows = fields.Integer(required=True, readonly=True, default=0)
    corrected_rows = fields.Integer(required=True, readonly=True, default=0)
    chunk_count = fields.Integer(required=True, readonly=True, default=0)
    state = fields.Selection(
        [
            ("queued", "Queued"),
            ("running", "Running"),
            ("completed", "Completed"),
            ("partial", "Partial failure"),
            ("failed", "Failed"),
        ],
        required=True,
        readonly=True,
        index=True,
        default="queued",
    )
    last_error_code = fields.Char(readonly=True, size=128)
    last_error_summary = fields.Char(readonly=True, size=240)
    started_at = fields.Datetime(readonly=True)
    completed_at = fields.Datetime(readonly=True, index=True)
    chunk_ids = fields.One2many(
        "odoo.ai.data.import.chunk",
        "session_id",
        string="Import chunks",
        readonly=True,
    )

    _sql_constraints = [
        (
            "data_import_session_uuid_unique",
            "unique(session_uuid)",
            "Assistant data import session id must be unique.",
        ),
        (
            "data_import_turn_request_unique",
            "unique(turn_id, request_fingerprint)",
            "Assistant data import request must be unique per turn.",
        ),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.su:
            raise AccessError("Assistant import sessions are host-owned")
        return super().create(vals_list)

    def write(self, vals):
        if not self.env.su:
            raise AccessError("Assistant import session lifecycle is host-owned")
        return super().write(vals)

    def unlink(self):
        if not self.env.su:
            raise AccessError("Assistant import session lifecycle is host-owned")
        return super().unlink()

    @api.model
    def inspect_csv_attachment(
        self,
        *,
        turn_uuid,
        attachment_id,
        target_model,
    ):
        """Inspect one current-turn CSV without widening model or field authority."""

        if self.env.su:
            raise AccessError("Assistant import inspection requires the effective user")
        attachment = _bound_attachment(
            self.env,
            turn_uuid=turn_uuid,
            attachment_id=attachment_id,
        )
        target_model = _target_model(self.env, target_model)
        safe_fields = _safe_import_fields(self.env, target_model)
        raw = _attachment_bytes(attachment)
        preview = _native_preview(
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
        examples = _column_examples(preview.get("preview"), headers)
        return {
            "attachment_id": attachment.id,
            "filename": attachment.filename,
            "mimetype": attachment.mimetype,
            "size": attachment.file_size,
            "fingerprint": f"sha256:{attachment.fingerprint}",
            "target_model": target_model,
            "headers": headers,
            "columns": examples,
            "safe_fields": safe_fields,
            "suggested_mapping": sorted(
                suggestions,
                key=lambda item: item["column_index"],
            ),
            "estimated_rows": _estimated_rows(preview),
            "import_options": _safe_import_options(preview.get("options")),
        }

    @api.model
    def validate_csv_request(
        self,
        *,
        turn_uuid,
        attachment_id,
        target_model,
        mapping,
        chunk_size=_DEFAULT_CHUNK_SIZE,
    ):
        """Return the host-normalized immutable request used by preview and execution."""

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
        attachment = _bound_attachment(
            self.env,
            turn_uuid=turn_uuid,
            attachment_id=attachment_id,
        )
        raw = _attachment_bytes(attachment)
        exact_rows = _mapped_rows(
            self.env,
            raw=raw,
            filename=attachment.filename,
            target_model=inspection["target_model"],
            fields_vector=fields_vector,
            options=inspection["import_options"],
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
            }
        )
        return {
            **inspection,
            "mapping": normalized_mapping,
            "chunk_size": chunk_size,
            "total_rows": len(exact_rows),
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
        """Persist and queue one idempotent import session after host plan authorization."""

        if self.env.su:
            raise AccessError("Assistant import creation requires the effective user")
        request = self.validate_csv_request(
            turn_uuid=turn_uuid,
            attachment_id=attachment_id,
            target_model=target_model,
            mapping=mapping,
            chunk_size=chunk_size,
        )
        if request["total_rows"] <= 0:
            raise DataImportWorkflowError("data_import_no_rows")
        attachment = _bound_attachment(
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
                "import_options_json": request["import_options"],
                "request_fingerprint": request["request_fingerprint"],
                "mapping_fingerprint": request["mapping_fingerprint"],
                "chunk_size": request["chunk_size"],
                "total_rows": request["total_rows"],
                "duplicate_rows": request["duplicate_rows"],
                "state": "queued",
            }
        )
        session._trigger_processing_cron()
        return session

    @api.model
    def status_for_current_user(self, session_uuid, *, recent_chunks=8):
        if self.env.su:
            raise AccessError("Assistant import status requires the effective user")
        if not isinstance(session_uuid, str) or len(session_uuid) != 32:
            raise DataImportWorkflowError("data_import_session_invalid")
        if type(recent_chunks) is not int or not 1 <= recent_chunks <= _MAX_RECENT_CHUNKS:
            raise DataImportWorkflowError("data_import_status_limit_invalid")
        session = self.search(
            [
                ("session_uuid", "=", session_uuid),
                ("owner_user_id", "=", self.env.uid),
                ("company_id", "=", self.env.company.id),
            ],
            limit=1,
        )
        if not session:
            raise DataImportWorkflowError("data_import_session_not_found")
        return session._public_status(recent_chunks=recent_chunks)

    def _public_status(self, *, recent_chunks=8):
        self.ensure_one()
        chunks = self.chunk_ids.sorted(
            key=lambda row: (row.sequence, row.id),
            reverse=True,
        )[:recent_chunks]
        return {
            "session_uuid": self.session_uuid,
            "state": self.state,
            "target_model": self.target_model,
            "filename": self.filename,
            "total_rows": self.total_rows,
            "imported_rows": self.imported_rows,
            "failed_rows": self.failed_rows,
            "corrected_rows": self.corrected_rows,
            "remaining_rows": max(
                0,
                self.total_rows - self.imported_rows - self.failed_rows,
            ),
            "duplicate_rows": self.duplicate_rows,
            "chunk_size": self.chunk_size,
            "chunk_count": self.chunk_count,
            "mapping_fingerprint": self.mapping_fingerprint,
            "last_error_code": self.last_error_code or "",
            "last_error_summary": self.last_error_summary or "",
            "chunks": [chunk._public_receipt() for chunk in reversed(chunks)],
        }

    @api.model
    def _cron_process_pending(self):
        """Process at most one chunk; transaction commit is the chunk receipt boundary."""

        system_model = self.with_user(SUPERUSER_ID)
        session = system_model._claim_next_session()
        if not session:
            return False
        try:
            with self.env.cr.savepoint():
                session._process_one_chunk()
        except DataImportChunkRejected as error:
            session._record_rejected_chunk(error)
        except Exception:  # noqa: BLE001 - cron boundary records only a sanitized failure
            session.write(
                {
                    "state": "failed",
                    "last_error_code": "data_import_processing_failed",
                    "last_error_summary": "The import worker could not process the next chunk.",
                    "completed_at": fields.Datetime.now(),
                }
            )
        if session.state == "queued":
            session._trigger_processing_cron()
        return True

    @api.model
    def _claim_next_session(self):
        self.env.cr.execute(
            """
            SELECT id
              FROM odoo_ai_data_import_session
             WHERE state = 'queued'
             ORDER BY id
             FOR UPDATE SKIP LOCKED
             LIMIT 1
            """
        )
        row = self.env.cr.fetchone()
        return self.browse(row[0]) if row else self.browse()

    def _process_one_chunk(self):
        self.ensure_one()
        if not self.env.su or self.state != "queued":
            raise DataImportWorkflowError("data_import_worker_binding_invalid")

        effective_env = _effective_user_env(self)
        _target_model(effective_env, self.target_model)
        safe_fields = _safe_import_fields(effective_env, self.target_model)
        mapping = _normalized_mapping(
            self.mapping_json,
            headers=list(self.headers_json or []),
            safe_fields=safe_fields,
        )
        fields_vector = _fields_vector(list(self.headers_json or []), mapping)
        raw = _session_bytes(self)
        options = _safe_import_options(self.import_options_json)
        options["skip"] = self.next_row
        options["limit"] = self.chunk_size

        wizard = _native_wizard(
            effective_env,
            raw=raw,
            filename=self.filename,
            target_model=self.target_model,
        )
        try:
            remaining, _import_fields = wizard._convert_import_data(  # noqa: SLF001
                fields_vector,
                dict(options),
            )
        except Exception as error:  # noqa: BLE001 - Odoo importer failures are sanitized
            raise DataImportWorkflowError("data_import_csv_invalid") from error

        input_count = min(self.chunk_size, len(remaining))
        if input_count <= 0:
            self.write(
                {
                    "state": "completed",
                    "completed_at": fields.Datetime.now(),
                    "last_error_code": False,
                    "last_error_summary": False,
                }
            )
            return

        sequence = self.chunk_count + 1
        row_start = self.next_row + 1
        row_end = self.next_row + input_count
        self.write(
            {
                "state": "running",
                "started_at": self.started_at or fields.Datetime.now(),
            }
        )

        dryrun = wizard.execute_import(
            fields_vector,
            list(self.headers_json),
            dict(options),
            dryrun=True,
        )
        dry_messages = dryrun.get("messages") if isinstance(dryrun, dict) else None
        if dry_messages:
            raise DataImportChunkRejected(
                sequence=sequence,
                row_start=row_start,
                row_end=row_end,
                input_count=input_count,
                messages=dry_messages,
            )

        result = wizard.execute_import(
            fields_vector,
            list(self.headers_json),
            dict(options),
            dryrun=False,
        )
        messages = result.get("messages") if isinstance(result, dict) else None
        if messages:
            raise DataImportChunkRejected(
                sequence=sequence,
                row_start=row_start,
                row_end=row_end,
                input_count=input_count,
                messages=messages,
            )
        record_ids = result.get("ids") if isinstance(result, dict) else None
        if (
            not isinstance(record_ids, list)
            or len(record_ids) != input_count
            or any(type(record_id) is not int or record_id <= 0 for record_id in record_ids)
        ):
            raise DataImportWorkflowError("data_import_result_invalid")

        nextrow = result.get("nextrow")
        if type(nextrow) is int and nextrow > self.next_row:
            next_row = nextrow
        else:
            next_row = self.next_row + input_count
        complete = nextrow == 0 or next_row >= self.total_rows
        receipt_fingerprint = _fingerprint(
            {
                "session": self.session_uuid,
                "sequence": sequence,
                "row_start": row_start,
                "row_end": row_end,
                "record_ids": record_ids,
                "mapping": self.mapping_fingerprint,
            }
        )
        self.env["odoo.ai.data.import.chunk"].with_user(SUPERUSER_ID).create(
            {
                "session_id": self.id,
                "sequence": sequence,
                "row_start": row_start,
                "row_end": row_end,
                "input_count": input_count,
                "imported_count": input_count,
                "failed_count": 0,
                "record_ids_json": record_ids,
                "messages_json": [],
                "state": "completed",
                "receipt_fingerprint": receipt_fingerprint,
                "completed_at": fields.Datetime.now(),
            }
        )
        values = {
            "state": "completed" if complete else "queued",
            "next_row": next_row,
            "imported_rows": self.imported_rows + input_count,
            "chunk_count": sequence,
            "last_error_code": False,
            "last_error_summary": False,
        }
        if complete:
            values["completed_at"] = fields.Datetime.now()
        self.write(values)

    def _record_rejected_chunk(self, error: DataImportChunkRejected):
        self.ensure_one()
        sequence = self.chunk_count + 1
        if sequence != error.sequence:
            raise DataImportWorkflowError("data_import_receipt_sequence_invalid")
        self.env["odoo.ai.data.import.chunk"].with_user(SUPERUSER_ID).create(
            {
                "session_id": self.id,
                "sequence": sequence,
                "row_start": error.row_start,
                "row_end": error.row_end,
                "input_count": error.input_count,
                "imported_count": 0,
                "failed_count": error.input_count,
                "record_ids_json": [],
                "messages_json": error.messages,
                "state": "rejected",
                "receipt_fingerprint": _fingerprint(
                    {
                        "session": self.session_uuid,
                        "sequence": sequence,
                        "row_start": error.row_start,
                        "row_end": error.row_end,
                        "failed_count": error.input_count,
                        "mapping": self.mapping_fingerprint,
                    }
                ),
                "completed_at": fields.Datetime.now(),
            }
        )
        self.write(
            {
                "state": "partial" if self.imported_rows else "failed",
                "failed_rows": self.failed_rows + error.input_count,
                "chunk_count": sequence,
                "last_error_code": error.code,
                "last_error_summary": (
                    f"{error.input_count} row(s) were rejected by Odoo validation; "
                    "no row from that chunk was written."
                ),
                "completed_at": fields.Datetime.now(),
            }
        )

    @api.model
    def _cron_cleanup_terminal(self):
        cutoff = fields.Datetime.now() - timedelta(days=_RETENTION_DAYS)
        expired = self.with_user(SUPERUSER_ID).search(
            [
                ("state", "in", list(_TERMINAL_STATES)),
                ("completed_at", "<", cutoff),
            ],
            order="completed_at, id",
            limit=100,
        )
        if expired:
            expired.unlink()
        return True

    def _trigger_processing_cron(self):
        cron = self.env.ref(
            "odoo_ai_assistant.ir_cron_assistant_data_import",
            raise_if_not_found=False,
        )
        if cron:
            cron._trigger()


class AssistantDataImportChunk(models.Model):
    _name = "odoo.ai.data.import.chunk"
    _description = "Odoo AI Assistant Data Import Chunk Receipt"
    _order = "session_id, sequence, id"

    session_id = fields.Many2one(
        "odoo.ai.data.import.session",
        required=True,
        readonly=True,
        index=True,
        ondelete="cascade",
    )
    sequence = fields.Integer(required=True, readonly=True, index=True)
    row_start = fields.Integer(required=True, readonly=True)
    row_end = fields.Integer(required=True, readonly=True)
    input_count = fields.Integer(required=True, readonly=True)
    imported_count = fields.Integer(required=True, readonly=True)
    failed_count = fields.Integer(required=True, readonly=True)
    record_ids_json = fields.Json(required=True, readonly=True, copy=False, default=list)
    messages_json = fields.Json(required=True, readonly=True, copy=False, default=list)
    state = fields.Selection(
        [("completed", "Completed"), ("rejected", "Rejected")],
        required=True,
        readonly=True,
        index=True,
    )
    receipt_fingerprint = fields.Char(required=True, readonly=True, index=True, size=71)
    completed_at = fields.Datetime(required=True, readonly=True, index=True)

    _sql_constraints = [
        (
            "data_import_chunk_session_sequence_unique",
            "unique(session_id, sequence)",
            "Assistant data import chunk sequence must be unique per session.",
        )
    ]

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.su:
            raise AccessError("Assistant import chunk receipts are host-owned")
        return super().create(vals_list)

    def write(self, vals):
        if not self.env.su:
            raise AccessError("Assistant import chunk receipts are immutable")
        return super().write(vals)

    def unlink(self):
        if not self.env.su:
            raise AccessError("Assistant import chunk receipts are host-owned")
        return super().unlink()

    def _public_receipt(self):
        self.ensure_one()
        return {
            "sequence": self.sequence,
            "row_start": self.row_start,
            "row_end": self.row_end,
            "input_count": self.input_count,
            "imported_count": self.imported_count,
            "failed_count": self.failed_count,
            "state": self.state,
            "record_ids": list(self.record_ids_json or [])[:_MAX_CHUNK_SIZE],
            "messages": list(self.messages_json or [])[:_MAX_PUBLIC_MESSAGES],
            "receipt_fingerprint": self.receipt_fingerprint,
            "completed_at": (
                fields.Datetime.to_string(self.completed_at)
                if self.completed_at
                else ""
            ),
        }


def _bound_attachment(env, *, turn_uuid, attachment_id):
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
    if (
        not attachment
        or attachment.expires_at < fields.Datetime.now()
        or attachment.mimetype != "text/csv"
        or not attachment.filename.lower().endswith(".csv")
    ):
        raise DataImportWorkflowError("data_import_attachment_invalid")
    return attachment


def _target_model(env, value):
    if not isinstance(value, str) or not agent_model_is_eligible(env, value):
        raise DataImportWorkflowError("data_import_model_not_allowed")
    model_set = env[value]
    try:
        model_set.browse().check_access("create")
    except (AccessError, MissingError, UserError, ValidationError):
        raise DataImportWorkflowError("data_import_create_access_denied") from None
    return value


def _safe_import_fields(env, target_model):
    try:
        allowed = visible_action_preview_fields(env, target_model)
        descriptions = env[target_model].fields_get(
            allfields=list(allowed),
            attributes=["string", "type", "required"],
        )
    except (TurnContextError, AccessError, MissingError, ValidationError, KeyError):
        raise DataImportWorkflowError("data_import_schema_unavailable") from None
    result = []
    for name in allowed:
        description = descriptions.get(name)
        if (
            not isinstance(description, dict)
            or description.get("type") not in _ALLOWED_FIELD_TYPES
        ):
            continue
        label = " ".join(str(description.get("string") or name).split())[:160] or name
        result.append(
            {
                "name": name,
                "label": label,
                "type": description["type"],
                "required": description.get("required") is True,
            }
        )
    if not result:
        raise DataImportWorkflowError("data_import_schema_unavailable")
    return result


def _native_wizard(env, *, raw, filename, target_model):
    return env["base_import.import"].create(
        {
            "res_model": target_model,
            "file_name": filename,
            "file_type": "text/csv",
            "file": raw,
        }
    )


def _native_preview(env, *, raw, filename, target_model):
    wizard = _native_wizard(
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
    except Exception as error:  # noqa: BLE001 - native import errors are sanitized
        raise DataImportWorkflowError("data_import_csv_invalid") from error
    if not isinstance(preview, dict) or preview.get("error"):
        raise DataImportWorkflowError("data_import_csv_invalid")
    return preview


def _headers(preview):
    raw = preview.get("headers")
    if not isinstance(raw, list) or not raw:
        raise DataImportWorkflowError("data_import_headers_missing")
    headers = []
    for value in raw:
        header = " ".join(str(value or "").replace("\x00", "").split())
        if not header:
            raise DataImportWorkflowError("data_import_headers_missing")
        headers.append(header[:_MAX_COLUMN_NAME])
    return headers


def _column_examples(raw_preview, headers):
    values = raw_preview if isinstance(raw_preview, list) else []
    result = []
    for index, header in enumerate(headers):
        raw_examples = values[index] if index < len(values) and isinstance(values[index], list) else []
        examples = []
        for value in raw_examples[:_MAX_SAMPLE_VALUES]:
            sample = " ".join(str(value or "").replace("\x00", "").split())
            examples.append(sample[:_MAX_SAMPLE_VALUE])
        result.append({"column_index": index, "column": header, "examples": examples})
    return result


def _estimated_rows(preview):
    value = preview.get("file_length")
    if type(value) is not int or value < 0:
        return 0
    return max(0, value - 1)


def _safe_import_options(value):
    source = value if isinstance(value, dict) else {}
    result = {
        "has_headers": True,
        "separator": source.get("separator", ""),
        "quoting": source.get("quoting", '"'),
    }
    for key in _SAFE_OPTION_KEYS:
        if key in {"separator", "quoting"}:
            continue
        item = source.get(key)
        if item is None or item is False or isinstance(item, (str, bool, int, float)):
            result[key] = item
    if not isinstance(result["separator"], str) or len(result["separator"]) > 4:
        raise DataImportWorkflowError("data_import_options_invalid")
    if not isinstance(result["quoting"], str) or len(result["quoting"]) > 4:
        raise DataImportWorkflowError("data_import_options_invalid")
    return result


def _normalized_mapping(mapping, *, headers, safe_fields):
    if not isinstance(mapping, list) or not mapping or len(mapping) > len(headers):
        raise DataImportWorkflowError("data_import_mapping_invalid")
    allowed = {item["name"] for item in safe_fields}
    result = []
    indices = set()
    fields_seen = set()
    for item in mapping:
        if not isinstance(item, dict) or set(item) != {"column_index", "field"}:
            raise DataImportWorkflowError("data_import_mapping_invalid")
        column_index = item.get("column_index")
        field_name = item.get("field")
        if (
            type(column_index) is not int
            or not 0 <= column_index < len(headers)
            or not isinstance(field_name, str)
            or field_name not in allowed
            or column_index in indices
            or field_name in fields_seen
        ):
            raise DataImportWorkflowError("data_import_mapping_invalid")
        indices.add(column_index)
        fields_seen.add(field_name)
        result.append(
            {
                "column_index": column_index,
                "column": headers[column_index],
                "field": field_name,
            }
        )
    return sorted(result, key=lambda item: item["column_index"])


def _fields_vector(headers, mapping):
    by_index = {item["column_index"]: item["field"] for item in mapping}
    return [by_index.get(index, False) for index in range(len(headers))]


def _mapped_rows(env, *, raw, filename, target_model, fields_vector, options):
    wizard = _native_wizard(
        env,
        raw=raw,
        filename=filename,
        target_model=target_model,
    )
    try:
        rows, _fields = wizard._convert_import_data(  # noqa: SLF001
            fields_vector,
            dict(options),
        )
    except Exception as error:  # noqa: BLE001 - native import errors are sanitized
        raise DataImportWorkflowError("data_import_csv_invalid") from error
    if not isinstance(rows, list):
        raise DataImportWorkflowError("data_import_csv_invalid")
    return rows


def _duplicate_rows(rows):
    seen = set()
    duplicates = 0
    for row in rows:
        key = tuple(str(value) for value in row)
        if key in seen:
            duplicates += 1
        else:
            seen.add(key)
    return duplicates


def _chunk_size(value):
    if type(value) is not int or not _MIN_CHUNK_SIZE <= value <= _MAX_CHUNK_SIZE:
        raise DataImportWorkflowError("data_import_chunk_size_invalid")
    return value


def _attachment_bytes(attachment):
    try:
        payload = attachment.data.encode("ascii") if isinstance(attachment.data, str) else attachment.data
        raw = base64.b64decode(payload, validate=True)
    except Exception as error:
        raise DataImportWorkflowError("data_import_attachment_invalid") from error
    if not raw or hashlib.sha256(raw).hexdigest() != attachment.fingerprint:
        raise DataImportWorkflowError("data_import_attachment_stale")
    return raw


def _session_bytes(session):
    try:
        payload = session.file_data.encode("ascii") if isinstance(session.file_data, str) else session.file_data
        raw = base64.b64decode(payload, validate=True)
    except Exception as error:
        raise DataImportWorkflowError("data_import_artifact_corrupt") from error
    if (
        not raw
        or len(raw) != session.file_size
        or hashlib.sha256(raw).hexdigest() != session.file_fingerprint
    ):
        raise DataImportWorkflowError("data_import_artifact_corrupt")
    return raw


def _effective_user_env(session):
    user = session.owner_user_id
    company = session.company_id
    if not user.active or company.id not in user.company_ids.ids:
        raise DataImportWorkflowError("data_import_effective_user_unavailable")
    context = {
        "allowed_company_ids": [company.id],
        "lang": user.lang or "en_US",
        "tz": user.tz or False,
    }
    env = api.Environment(session.env.cr, user.id, context, su=False)
    if env.su:
        raise DataImportWorkflowError("data_import_effective_user_invalid")
    return env


def _sanitize_messages(messages):
    if not isinstance(messages, list):
        return []
    result = []
    for item in messages[:_MAX_PUBLIC_MESSAGES]:
        if not isinstance(item, dict):
            continue
        kind = item.get("type")
        message = item.get("message")
        if kind not in {"error", "warning"}:
            kind = "error"
        public = " ".join(str(message or "Import validation failed.").replace("\x00", "").split())
        result.append({"type": kind, "message": public[:_MAX_PUBLIC_MESSAGE]})
    return result


def _fingerprint(value):
    raw = json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


__all__ = [
    "AssistantDataImportChunk",
    "AssistantDataImportSession",
    "DataImportWorkflowError",
]
