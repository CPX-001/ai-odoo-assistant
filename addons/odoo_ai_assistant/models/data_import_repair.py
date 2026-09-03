"""Phase 11 deterministic cleanup and repair for durable CSV imports."""

from __future__ import annotations

import math

from odoo import SUPERUSER_ID, api, fields, models
from odoo.exceptions import AccessError

from .data_import import (
    _MAX_CHUNKS_PER_SESSION,
    DataImportWorkflowError,
    _bound_attachment,
    _duplicate_rows,
    _fingerprint,
    _import_fields,
    _normalized_mapping,
    _prepared_rows_fingerprint,
    _safe_import_fields,
    _target_model,
    _validate_prepared_rows,
)

_MAX_CLEANUP_RULES = 32
_MAX_RULE_VALUE = 1024
_MAX_CLEANUP_SAMPLES = 12
_MAX_REJECTED_ROWS = 20
_MAX_REPAIR_CORRECTIONS = 64
_MAX_REPAIR_HISTORY = 16
_TEXT_CLEANUP_TYPES = frozenset({"char", "selection", "text"})
_CLEANUP_OPERATIONS = frozenset(
    {"normalize_whitespace", "replace_exact", "set_if_empty", "trim"}
)
_OPERATION_ORDER = {
    "trim": 0,
    "normalize_whitespace": 1,
    "replace_exact": 2,
    "set_if_empty": 3,
}


class AssistantDataImportSessionRepair(models.Model):
    _inherit = "odoo.ai.data.import.session"

    cleanup_rules_json = fields.Json(
        readonly=True,
        copy=False,
        default=list,
        groups="base.group_system",
    )
    prepared_changed_rows_json = fields.Json(
        readonly=True,
        copy=False,
        default=list,
        groups="base.group_system",
    )
    cleanup_fingerprint = fields.Char(readonly=True, index=True, size=71)
    planned_corrected_rows = fields.Integer(readonly=True, default=0)
    repair_revision = fields.Integer(readonly=True, default=0)
    last_repair_fingerprint = fields.Char(readonly=True, index=True, size=71)
    repair_history_json = fields.Json(
        readonly=True,
        copy=False,
        default=list,
        groups="base.group_system",
    )

    @api.model
    def _prepare_cleanup_request(
        self,
        *,
        turn_uuid,
        attachment_id,
        target_model,
        mapping,
        cleanup_rules,
        chunk_size=250,
    ):
        if self.env.su:
            raise AccessError("Assistant import cleanup requires the effective user")
        request = self._prepare_csv_request(
            turn_uuid=turn_uuid,
            attachment_id=attachment_id,
            target_model=target_model,
            mapping=mapping,
            chunk_size=chunk_size,
        )
        rules = _normalize_cleanup_rules(
            cleanup_rules,
            import_fields=request["import_fields"],
            safe_fields=request["safe_fields"],
        )
        cleaned_rows, changed_rows, samples = _apply_cleanup_rules(
            request["prepared_rows"],
            import_fields=request["import_fields"],
            rules=rules,
        )
        if not changed_rows:
            raise DataImportWorkflowError("data_import_cleanup_no_effect")
        _validate_prepared_rows(
            cleaned_rows,
            import_fields=request["import_fields"],
        )
        cleaned_fingerprint = _prepared_rows_fingerprint(
            request["import_fields"],
            cleaned_rows,
        )
        duplicate_rows_after = _duplicate_rows(cleaned_rows)
        cleanup_fingerprint = _fingerprint(
            {
                "rules": rules,
                "before": request["prepared_rows_fingerprint"],
                "after": cleaned_fingerprint,
            }
        )
        request_fingerprint = _fingerprint(
            {
                "base_request": request["request_fingerprint"],
                "cleanup": cleanup_fingerprint,
                "prepared_rows": cleaned_fingerprint,
            }
        )
        return {
            **request,
            "prepared_rows": cleaned_rows,
            "prepared_rows_fingerprint": cleaned_fingerprint,
            "duplicate_rows_before": request["duplicate_rows"],
            "duplicate_rows": duplicate_rows_after,
            "cleanup_rules": rules,
            "cleanup_fingerprint": cleanup_fingerprint,
            "changed_rows": sorted(changed_rows),
            "planned_corrected_rows": len(changed_rows),
            "cleanup_samples": samples,
            "request_fingerprint": request_fingerprint,
        }

    @api.model
    def create_clean_csv_session(
        self,
        *,
        turn_uuid,
        attachment_id,
        target_model,
        mapping,
        cleanup_rules,
        chunk_size=250,
    ):
        if self.env.su:
            raise AccessError("Assistant import creation requires the effective user")
        request = self._prepare_cleanup_request(
            turn_uuid=turn_uuid,
            attachment_id=attachment_id,
            target_model=target_model,
            mapping=mapping,
            cleanup_rules=cleanup_rules,
            chunk_size=chunk_size,
        )
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
                "cleanup_rules_json": request["cleanup_rules"],
                "prepared_changed_rows_json": request["changed_rows"],
                "cleanup_fingerprint": request["cleanup_fingerprint"],
                "planned_corrected_rows": request["planned_corrected_rows"],
                "state": "queued",
            }
        )
        session._trigger_processing_cron()
        return session

    @api.model
    def cleanup_metadata_for_current_user(self, session_uuid):
        session = self._owned_import_session(session_uuid)
        system_session = session.with_user(SUPERUSER_ID)
        return {
            "session_uuid": system_session.session_uuid,
            "state": system_session.state,
            "cleanup_fingerprint": system_session.cleanup_fingerprint or "",
            "planned_corrected_rows": system_session.planned_corrected_rows,
            "corrected_rows": system_session.corrected_rows,
            "repair_revision": system_session.repair_revision,
            "prepared_rows_fingerprint": system_session.prepared_rows_fingerprint,
            "planned_chunk_count": system_session.planned_chunk_count,
        }

    @api.model
    def inspect_rejected_for_current_user(self, session_uuid, *, max_rows=8):
        session = self._owned_import_session(session_uuid)
        if type(max_rows) is not int or not 1 <= max_rows <= _MAX_REJECTED_ROWS:
            raise DataImportWorkflowError("data_import_rejected_limit_invalid")
        system_session = session.with_user(SUPERUSER_ID)
        rejected = _active_rejected_chunk(system_session)
        import_fields = _revalidated_import_fields(self.env, system_session)
        rows = system_session.prepared_rows_json
        _validate_prepared_rows(rows, import_fields=import_fields)
        start = rejected.row_start - 1
        end = min(rejected.row_end, rejected.row_start - 1 + max_rows)
        public_rows = []
        for row_index in range(start, end):
            row = rows[row_index]
            public_rows.append(
                {
                    "row": row_index + 1,
                    "values": {
                        field_name: _public_cell(row[column_index])
                        for column_index, field_name in enumerate(import_fields)
                    },
                }
            )
        return {
            "session_uuid": system_session.session_uuid,
            "state": system_session.state,
            "target_model": system_session.target_model,
            "rejected_sequence": rejected.sequence,
            "row_start": rejected.row_start,
            "row_end": rejected.row_end,
            "messages": list(rejected.messages_json or [])[:8],
            "rows": public_rows,
            "repair_revision": system_session.repair_revision,
            "mapping_fingerprint": system_session.mapping_fingerprint,
            "prepared_rows_fingerprint": system_session.prepared_rows_fingerprint,
        }

    @api.model
    def _prepare_repair_request(self, *, session_uuid, corrections):
        if self.env.su:
            raise AccessError("Assistant import repair requires the effective user")
        session = self._owned_import_session(session_uuid)
        system_session = session.with_user(SUPERUSER_ID)
        rejected = _active_rejected_chunk(system_session)
        import_fields = _revalidated_import_fields(self.env, system_session)
        rows = system_session.prepared_rows_json
        _validate_prepared_rows(rows, import_fields=import_fields)
        normalized = _normalize_repair_corrections(
            corrections,
            import_fields=import_fields,
            row_start=rejected.row_start,
            row_end=rejected.row_end,
            rows=rows,
        )
        prepared_rows = [list(row) for row in rows]
        public_corrections = []
        corrected_row_indices = set()
        positions = {field_name: index for index, field_name in enumerate(import_fields)}
        for correction in normalized:
            row_index = correction["row"] - 1
            column_index = positions[correction["field"]]
            before = prepared_rows[row_index][column_index]
            after = correction["value"]
            if before == after:
                raise DataImportWorkflowError("data_import_repair_no_effect")
            prepared_rows[row_index][column_index] = after
            corrected_row_indices.add(row_index)
            public_corrections.append(
                {
                    "row": correction["row"],
                    "field": correction["field"],
                    "before": _public_cell(before),
                    "after": _public_cell(after),
                }
            )

        _validate_prepared_rows(prepared_rows, import_fields=import_fields)
        new_fingerprint = _prepared_rows_fingerprint(import_fields, prepared_rows)
        changed_rows = _changed_row_indices(
            system_session.prepared_changed_rows_json,
            total_rows=system_session.total_rows,
        )
        changed_rows.update(corrected_row_indices)
        if system_session.failed_rows < rejected.input_count:
            raise DataImportWorkflowError("data_import_repair_state_invalid")
        remaining_rows = system_session.total_rows - system_session.next_row
        if remaining_rows <= 0:
            raise DataImportWorkflowError("data_import_repair_state_invalid")
        planned_chunk_count = system_session.chunk_count + math.ceil(
            remaining_rows / system_session.chunk_size
        )
        if planned_chunk_count > _MAX_CHUNKS_PER_SESSION:
            raise DataImportWorkflowError("data_import_too_many_chunks")
        next_revision = system_session.repair_revision + 1
        repair_fingerprint = _fingerprint(
            {
                "session": system_session.session_uuid,
                "revision": next_revision,
                "rejected_receipt": rejected.receipt_fingerprint,
                "before": system_session.prepared_rows_fingerprint,
                "after": new_fingerprint,
                "corrections": normalized,
            }
        )
        return {
            "session": system_session,
            "session_uuid": system_session.session_uuid,
            "target_model": system_session.target_model,
            "rejected_sequence": rejected.sequence,
            "row_start": rejected.row_start,
            "row_end": rejected.row_end,
            "repair_revision": next_revision,
            "repair_fingerprint": repair_fingerprint,
            "corrections": public_corrections,
            "corrected_rows_planned": len(corrected_row_indices),
            "prepared_rows": prepared_rows,
            "prepared_rows_fingerprint": new_fingerprint,
            "changed_rows": sorted(changed_rows),
            "planned_corrected_rows": len(changed_rows),
            "duplicate_rows": _duplicate_rows(prepared_rows),
            "failed_rows": system_session.failed_rows - rejected.input_count,
            "planned_chunk_count": planned_chunk_count,
            "remaining_rows": remaining_rows,
        }

    @api.model
    def resume_with_corrections(self, *, session_uuid, corrections):
        plan = self._prepare_repair_request(
            session_uuid=session_uuid,
            corrections=corrections,
        )
        session = plan["session"]
        history = _repair_history(session.repair_history_json)
        history.append(
            {
                "revision": plan["repair_revision"],
                "rejected_sequence": plan["rejected_sequence"],
                "row_start": plan["row_start"],
                "row_end": plan["row_end"],
                "corrected_rows": plan["corrected_rows_planned"],
                "repair_fingerprint": plan["repair_fingerprint"],
                "prepared_rows_fingerprint": plan["prepared_rows_fingerprint"],
            }
        )
        history = history[-_MAX_REPAIR_HISTORY:]
        session.write(
            {
                "prepared_rows_json": plan["prepared_rows"],
                "prepared_rows_fingerprint": plan["prepared_rows_fingerprint"],
                "prepared_changed_rows_json": plan["changed_rows"],
                "planned_corrected_rows": plan["planned_corrected_rows"],
                "duplicate_rows": plan["duplicate_rows"],
                "failed_rows": plan["failed_rows"],
                "planned_chunk_count": plan["planned_chunk_count"],
                "repair_revision": plan["repair_revision"],
                "last_repair_fingerprint": plan["repair_fingerprint"],
                "repair_history_json": history,
                "state": "queued",
                "last_error_code": False,
                "last_error_summary": False,
                "completed_at": False,
            }
        )
        session._trigger_processing_cron()
        return session

    @api.model
    def repair_metadata_for_current_user(self, session_uuid):
        session = self._owned_import_session(session_uuid)
        system_session = session.with_user(SUPERUSER_ID)
        return {
            "session_uuid": system_session.session_uuid,
            "state": system_session.state,
            "repair_revision": system_session.repair_revision,
            "last_repair_fingerprint": system_session.last_repair_fingerprint or "",
            "prepared_rows_fingerprint": system_session.prepared_rows_fingerprint,
            "planned_corrected_rows": system_session.planned_corrected_rows,
            "corrected_rows": system_session.corrected_rows,
            "planned_chunk_count": system_session.planned_chunk_count,
        }

    @api.model
    def _owned_import_session(self, session_uuid):
        if self.env.su:
            raise AccessError("Assistant import access requires the effective user")
        if not isinstance(session_uuid, str) or len(session_uuid) != 32:
            raise DataImportWorkflowError("data_import_session_invalid")
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
        return session

    def _process_one_chunk(self):
        self.ensure_one()
        changed_rows = _changed_row_indices(
            self.prepared_changed_rows_json,
            total_rows=self.total_rows,
        )
        if self.planned_corrected_rows != len(changed_rows):
            raise DataImportWorkflowError("data_import_correction_metadata_invalid")
        before_next_row = self.next_row
        before_imported_rows = self.imported_rows
        before_corrected_rows = self.corrected_rows
        result = super()._process_one_chunk()
        imported_delta = self.imported_rows - before_imported_rows
        if imported_delta > 0:
            correction_delta = sum(
                1
                for row_index in changed_rows
                if before_next_row <= row_index < before_next_row + imported_delta
            )
            if correction_delta:
                self.write(
                    {
                        "corrected_rows": before_corrected_rows + correction_delta,
                    }
                )
        return result


def _normalize_cleanup_rules(value, *, import_fields, safe_fields):
    if not isinstance(value, list) or not 1 <= len(value) <= _MAX_CLEANUP_RULES:
        raise DataImportWorkflowError("data_import_cleanup_invalid")
    safe_by_name = {item["name"]: item for item in safe_fields}
    mapped_fields = set(import_fields)
    normalized = []
    unique_keys = set()
    for item in value:
        if not isinstance(item, dict):
            raise DataImportWorkflowError("data_import_cleanup_invalid")
        field_name = item.get("field")
        operation = item.get("operation")
        if (
            not isinstance(field_name, str)
            or field_name not in mapped_fields
            or field_name not in safe_by_name
            or operation not in _CLEANUP_OPERATIONS
        ):
            raise DataImportWorkflowError("data_import_cleanup_invalid")

        if operation in {"trim", "normalize_whitespace"}:
            if set(item) != {"field", "operation"}:
                raise DataImportWorkflowError("data_import_cleanup_invalid")
            if safe_by_name[field_name]["type"] not in _TEXT_CLEANUP_TYPES:
                raise DataImportWorkflowError("data_import_cleanup_invalid")
            key = (field_name, operation)
            normalized_item = {
                "field": field_name,
                "operation": operation,
            }
        elif operation == "replace_exact":
            if set(item) != {"field", "operation", "match", "value"}:
                raise DataImportWorkflowError("data_import_cleanup_invalid")
            match = _rule_value(item.get("match"), code="data_import_cleanup_invalid")
            replacement = _rule_value(
                item.get("value"), code="data_import_cleanup_invalid"
            )
            key = (field_name, operation, match)
            normalized_item = {
                "field": field_name,
                "operation": operation,
                "match": match,
                "value": replacement,
            }
        else:
            if set(item) != {"field", "operation", "value"}:
                raise DataImportWorkflowError("data_import_cleanup_invalid")
            replacement = _rule_value(
                item.get("value"), code="data_import_cleanup_invalid"
            )
            key = (field_name, operation)
            normalized_item = {
                "field": field_name,
                "operation": operation,
                "value": replacement,
            }
        if key in unique_keys:
            raise DataImportWorkflowError("data_import_cleanup_invalid")
        unique_keys.add(key)
        normalized.append(normalized_item)

    positions = {field_name: index for index, field_name in enumerate(import_fields)}
    return sorted(
        normalized,
        key=lambda item: (
            positions[item["field"]],
            _OPERATION_ORDER[item["operation"]],
            item.get("match", ""),
            item.get("value", ""),
        ),
    )


def _apply_cleanup_rules(rows, *, import_fields, rules):
    positions = {field_name: index for index, field_name in enumerate(import_fields)}
    plan = {}
    for rule in rules:
        field_plan = plan.setdefault(
            rule["field"],
            {
                "trim": False,
                "normalize_whitespace": False,
                "replacements": {},
                "set_if_empty": None,
            },
        )
        operation = rule["operation"]
        if operation == "trim":
            field_plan["trim"] = True
        elif operation == "normalize_whitespace":
            field_plan["normalize_whitespace"] = True
        elif operation == "replace_exact":
            field_plan["replacements"][rule["match"]] = rule["value"]
        else:
            field_plan["set_if_empty"] = rule["value"]

    cleaned_rows = []
    changed_rows = set()
    samples = []
    for row_index, source_row in enumerate(rows):
        row = list(source_row)
        row_changed = False
        for field_name in import_fields:
            field_plan = plan.get(field_name)
            if not field_plan:
                continue
            column_index = positions[field_name]
            before = row[column_index]
            after = before
            if field_plan["trim"]:
                after = after.strip()
            if field_plan["normalize_whitespace"]:
                after = " ".join(after.split())
            if after in field_plan["replacements"]:
                after = field_plan["replacements"][after]
            if not after.strip() and field_plan["set_if_empty"] is not None:
                after = field_plan["set_if_empty"]
            if after != before:
                row[column_index] = after
                row_changed = True
                if len(samples) < _MAX_CLEANUP_SAMPLES:
                    samples.append(
                        {
                            "row": row_index + 1,
                            "field": field_name,
                            "before": _public_cell(before),
                            "after": _public_cell(after),
                        }
                    )
        if row_changed:
            changed_rows.add(row_index)
        if not any(value for value in row):
            raise DataImportWorkflowError("data_import_cleanup_removes_row")
        cleaned_rows.append(row)
    return cleaned_rows, changed_rows, samples


def _normalize_repair_corrections(
    value,
    *,
    import_fields,
    row_start,
    row_end,
    rows,
):
    if not isinstance(value, list) or not 1 <= len(value) <= _MAX_REPAIR_CORRECTIONS:
        raise DataImportWorkflowError("data_import_repair_invalid")
    mapped_fields = set(import_fields)
    positions = {field_name: index for index, field_name in enumerate(import_fields)}
    normalized = []
    seen = set()
    for item in value:
        if not isinstance(item, dict) or set(item) != {"row", "field", "value"}:
            raise DataImportWorkflowError("data_import_repair_invalid")
        row_number = item.get("row")
        field_name = item.get("field")
        replacement = _rule_value(item.get("value"), code="data_import_repair_invalid")
        if (
            type(row_number) is not int
            or not row_start <= row_number <= row_end
            or row_number > len(rows)
            or not isinstance(field_name, str)
            or field_name not in mapped_fields
        ):
            raise DataImportWorkflowError("data_import_repair_invalid")
        key = (row_number, field_name)
        if key in seen:
            raise DataImportWorkflowError("data_import_repair_invalid")
        seen.add(key)
        if rows[row_number - 1][positions[field_name]] == replacement:
            raise DataImportWorkflowError("data_import_repair_no_effect")
        normalized.append(
            {
                "row": row_number,
                "field": field_name,
                "value": replacement,
            }
        )
    return sorted(
        normalized,
        key=lambda item: (item["row"], positions[item["field"]]),
    )


def _revalidated_import_fields(env, system_session):
    _target_model(env, system_session.target_model)
    safe_fields = _safe_import_fields(env, system_session.target_model)
    mapping = _normalized_mapping(
        system_session.mapping_json,
        headers=list(system_session.headers_json or []),
        safe_fields=safe_fields,
        allow_persisted_column=True,
    )
    expected = [item["field"] for item in mapping]
    import_fields = _import_fields(system_session.import_fields_json)
    if import_fields != expected:
        raise DataImportWorkflowError("data_import_mapping_stale")
    return import_fields


def _active_rejected_chunk(system_session):
    if system_session.state not in {"partial", "failed"}:
        raise DataImportWorkflowError("data_import_repair_state_invalid")
    rejected = system_session.chunk_ids.filtered(
        lambda item: item.state == "rejected"
    ).sorted(
        key=lambda item: (item.sequence, item.id),
        reverse=True,
    )[:1]
    if (
        not rejected
        or rejected.sequence != system_session.chunk_count
        or rejected.row_start != system_session.next_row + 1
        or rejected.row_end != system_session.next_row + rejected.input_count
    ):
        raise DataImportWorkflowError("data_import_repair_state_invalid")
    return rejected


def _changed_row_indices(value, *, total_rows):
    if value in (None, False):
        return set()
    if not isinstance(value, list):
        raise DataImportWorkflowError("data_import_correction_metadata_invalid")
    result = set()
    for item in value:
        if type(item) is not int or not 0 <= item < total_rows or item in result:
            raise DataImportWorkflowError("data_import_correction_metadata_invalid")
        result.add(item)
    return result


def _repair_history(value):
    if value in (None, False):
        return []
    if (
        not isinstance(value, list)
        or len(value) > _MAX_REPAIR_HISTORY
        or any(not isinstance(item, dict) for item in value)
    ):
        raise DataImportWorkflowError("data_import_repair_history_invalid")
    return [dict(item) for item in value]


def _rule_value(value, *, code):
    if not isinstance(value, str) or len(value) > _MAX_RULE_VALUE or "\x00" in value:
        raise DataImportWorkflowError(code)
    return value


def _public_cell(value):
    if not isinstance(value, str):
        return ""
    return (
        value.replace("\x00", "")
        .replace("\r", "\\r")
        .replace("\n", "\\n")
        .replace("\t", "\\t")[:240]
    )


__all__ = ["AssistantDataImportSessionRepair"]
