"""Effect-free runtime validation for normalized batch rows under the real Odoo user."""

from __future__ import annotations

from odoo.exceptions import AccessError, MissingError, ValidationError

from .action_tools import (
    _BLOCKED_FIELDS,
    _BLOCKED_MODEL_PREFIXES,
    _BLOCKED_MODELS,
    _SENSITIVE_FIELD_PARTS,
    _VALUE_KIND_BY_FIELD_TYPE,
)
from .batch_payload import batch_fields, parse_batch
from .orm_tools import OrmToolError

MAX_BATCH_PREFLIGHT_ROWS = 50


class DelegatedBatchPreflightExecutor:
    """Validate batch targets/values without invoking any mutating ORM operation."""

    def preflight(self, *, env, batch: object, max_records: int) -> dict[str, object]:
        if type(max_records) is not int or not 1 <= max_records <= MAX_BATCH_PREFLIGHT_ROWS:
            raise OrmToolError("scope_denied", 403)
        parsed = parse_batch(batch, max_rows=max_records)
        model = parsed["model"]
        if model in _BLOCKED_MODELS or any(
            model.startswith(prefix) for prefix in _BLOCKED_MODEL_PREFIXES
        ):
            raise OrmToolError("action_target_not_allowed", 403)
        try:
            model_set = env[model]
        except KeyError:
            raise OrmToolError("action_target_not_allowed", 403) from None

        metadata = _runtime_metadata(model_set, parsed)
        accepted: list[str] = []
        issues: list[dict[str, str]] = []
        for item in parsed["items"]:
            code = _row_issue(env, model_set, parsed["operation"], item, metadata)
            if code is None:
                accepted.append(item["source_ref"])
            else:
                issues.append({"source_ref": item["source_ref"], "error_code": code})
        return {
            "accepted_source_refs": accepted,
            "issues": issues,
            "model": model,
            "operation": parsed["operation"],
        }


def _runtime_metadata(model_set, batch: dict[str, object]) -> dict[str, dict[str, object]]:
    operation = batch["operation"]
    try:
        model_set.browse().check_access("read")
        if operation == "delete":
            model_set.browse().check_access("unlink")
            return {}
        if operation == "create":
            model_set.browse().check_access("create")
        else:
            model_set.browse().check_access("write")
        fields = batch_fields(batch)
        if not fields:
            raise OrmToolError("field_not_allowed", 403)
        model_set.check_field_access_rights("write", list(fields))
        descriptions = model_set.fields_get(
            list(fields),
            attributes=["type", "readonly", "required", "relation", "selection"],
        )
    except OrmToolError:
        raise
    except (AccessError, MissingError, ValidationError):
        raise OrmToolError("access_denied", 403) from None
    if not isinstance(descriptions, dict) or set(descriptions) != set(fields):
        raise OrmToolError("field_not_allowed", 403)
    for field in fields:
        if field in _BLOCKED_FIELDS or any(
            part in field.lower() for part in _SENSITIVE_FIELD_PARTS
        ):
            raise OrmToolError("field_not_allowed", 403)
        description = descriptions[field]
        if (
            not isinstance(description, dict)
            or _VALUE_KIND_BY_FIELD_TYPE.get(description.get("type")) is None
            or description.get("readonly") is not False
        ):
            raise OrmToolError("field_not_allowed", 403)
    return descriptions


def _row_issue(env, model_set, operation: str, item, metadata) -> str | None:
    try:
        if operation != "create":
            record = model_set.browse([item["record_id"]])
            record.check_access("read")
            record.check_access("unlink" if operation == "delete" else "write")
            if len(record.exists()) != 1:
                return "target_not_found"
        if operation == "delete":
            return None
        assignments = item["values"] if operation == "create" else item["changes"]
        for assignment in assignments:
            description = metadata[assignment["field"]]
            tagged = assignment["value"]
            expected_kind = _VALUE_KIND_BY_FIELD_TYPE[description["type"]]
            if tagged["kind"] != expected_kind:
                return "write_schema_mismatch"
            value = tagged["value"]
            if description.get("required") is True and (
                value is None or expected_kind == "text" and value == ""
            ):
                return "required_value_missing"
            if expected_kind == "selection" and value is not None:
                options = description.get("selection") or []
                allowed = {
                    option[0]
                    for option in options
                    if isinstance(option, (list, tuple))
                    and len(option) == 2
                    and isinstance(option[0], str)
                }
                if value not in allowed:
                    return "selection_value_invalid"
            if expected_kind == "many2one" and value is not None:
                relation = description.get("relation")
                if not isinstance(relation, str):
                    return "relation_invalid"
                related = env[relation].browse([value])
                related.check_access("read")
                if len(related.exists()) != 1:
                    return "relation_not_found"
        return None
    except (AccessError, MissingError):
        return "access_denied"
    except ValidationError:
        return "business_rule_rejected"
    except KeyError:
        return "relation_invalid"
