"""Bounded host-owned Odoo workflows composed inside one capability contract.

The model still proposes one CapabilityDefinition.  The host validates a small dependency graph,
resolves only typed references to records created by earlier nodes, executes the graph in the
current Odoo transaction and verifies every created record.  This avoids a parallel action registry
and does not expose arbitrary methods, Python, SQL or shell execution.
"""

from __future__ import annotations

import re

from odoo.exceptions import AccessError, MissingError, UserError, ValidationError

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
from .odoo_actions import (
    _fingerprint,
    _has_access,
    _model_name,
    _model_set,
    _read_values,
    _record,
    _validate_values,
    _verification_values,
    _write_descriptions,
)

_MAX_WORKFLOW_STEPS = 5
_MAX_ROWS_PER_STEP = 50
_MAX_TOTAL_ROWS = 100
_MAX_INPUT_BYTES = 192 * 1024
_MAX_OUTPUT_BYTES = 192 * 1024
_STEP_ID = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_FIELD = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")

_REFERENCE_SCHEMA = {
    "type": "object",
    "properties": {
        "$ref": {
            "type": "object",
            "properties": {
                "step": {"type": "string", "minLength": 1, "maxLength": 64},
                "record_index": {"type": "integer", "minimum": 0, "maximum": 49},
            },
            "required": ["step", "record_index"],
            "additionalProperties": False,
        }
    },
    "required": ["$ref"],
    "additionalProperties": False,
}
_WORKFLOW_INPUT = {
    "type": "object",
    "properties": {
        "operation": {"type": "string", "enum": ["create_graph"]},
        "steps": {
            "type": "array",
            "minItems": 2,
            "maxItems": _MAX_WORKFLOW_STEPS,
            "items": {
                "type": "object",
                "properties": {
                    "step_id": {"type": "string", "minLength": 1, "maxLength": 64},
                    "model": {"type": "string", "minLength": 1, "maxLength": 128},
                    "rows": {
                        "type": "array",
                        "minItems": 1,
                        "maxItems": _MAX_ROWS_PER_STEP,
                        "items": {"type": "object"},
                    },
                },
                "required": ["step_id", "model", "rows"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["operation", "steps"],
    "additionalProperties": False,
}
_WORKFLOW_OUTPUT = {
    "type": "object",
    "properties": {
        "operation": {"type": "string", "enum": ["create_graph"]},
        "steps": {
            "type": "array",
            "minItems": 2,
            "maxItems": _MAX_WORKFLOW_STEPS,
            "items": {
                "type": "object",
                "properties": {
                    "step_id": {"type": "string"},
                    "model": {"type": "string"},
                    "record_ids": {
                        "type": "array",
                        "minItems": 1,
                        "maxItems": _MAX_ROWS_PER_STEP,
                        "items": {"type": "integer", "minimum": 1},
                    },
                    "count": {"type": "integer", "minimum": 1},
                },
                "required": ["step_id", "model", "record_ids", "count"],
                "additionalProperties": False,
            },
        },
        "total_count": {"type": "integer", "minimum": 2, "maximum": _MAX_TOTAL_ROWS},
    },
    "required": ["operation", "steps", "total_count"],
    "additionalProperties": False,
}


def _workflow_preview(context: CapabilityContext, arguments):
    steps = _validated_templates(context, arguments)
    rows = []
    for step in steps:
        for index, row in enumerate(step["rows"]):
            rows.append(
                {
                    "display_name": _row_label(step["step_id"], index, row),
                    "model": step["model"],
                    "step_id": step["step_id"],
                    "values": row,
                }
            )
    summary = {
        "operation": "create_graph",
        "count": len(rows),
        "steps": [
            {
                "step_id": step["step_id"],
                "model": step["model"],
                "count": len(step["rows"]),
            }
            for step in steps
        ],
        "rows": rows,
    }
    return CapabilityPreview(
        summary=summary,
        precondition_fingerprint=_fingerprint(
            {"operation": "create_graph", "steps": steps}
        ),
    )


def _workflow_verify(context: CapabilityContext, arguments):
    templates = _validated_templates(context, arguments)
    result = _workflow_result(context)
    if len(templates) != len(result["steps"]):
        return CapabilityVerification(verified=False, summary={"count": 0})
    resolved = {}
    verified_count = 0
    for template, outcome in zip(templates, result["steps"], strict=True):
        if (
            outcome["step_id"] != template["step_id"]
            or outcome["model"] != template["model"]
            or outcome["count"] != len(template["rows"])
        ):
            return CapabilityVerification(verified=False, summary={"count": verified_count})
        rows = _resolve_rows(context, template, resolved)
        for record_id, expected in zip(outcome["record_ids"], rows, strict=True):
            record = _record(context, template["model"], record_id, access="read")
            if _read_values(record, expected) != _verification_values(record, expected):
                return CapabilityVerification(
                    verified=False,
                    summary={"model": template["model"], "record_id": record_id},
                )
            verified_count += 1
        resolved[template["step_id"]] = outcome
    return CapabilityVerification(
        verified=verified_count == result["total_count"],
        summary={"operation": "create_graph", "count": verified_count},
    )


@tool(
    name="odoo.workflow.batch_create_graph",
    title="Run a related-record creation workflow",
    description=(
        "Create 2 to 5 ordered Odoo record batches in one bounded host-owned workflow. Later "
        "rows may set a many2one field to a record created by an earlier step using "
        '{"$ref":{"step":"step_id","record_index":0}}. Use this when one user request '
        "requires creating records and then using those exact records in later creates, including "
        "mandatory synthetic prerequisites inferred from schema for a test-data outcome even when "
        "the user did not name those prerequisite models. The host "
        "validates every model, field, relation, row and reference, runs all steps in one Odoo "
        "transaction, and verifies every result."
    ),
    input_schema=_WORKFLOW_INPUT,
    output_schema=_WORKFLOW_OUTPUT,
    risk=CapabilityRisk.ACTION,
    effect=CapabilityEffect.INTERNAL_REVERSIBLE,
    exposure=CapabilityExposure.PLAN,
    approval=CapabilityApproval.POLICY,
    tags=("odoo", "action", "workflow", "batch", "write", "create", "related"),
    preview=_workflow_preview,
    verify=_workflow_verify,
    max_calls=2,
    max_input_bytes=_MAX_INPUT_BYTES,
    max_output_bytes=_MAX_OUTPUT_BYTES,
)
def batch_create_graph(context: CapabilityContext, arguments):
    templates = _validated_templates(context, arguments)
    outcomes = []
    resolved = {}
    for template in templates:
        rows = _resolve_rows(context, template, resolved)
        try:
            records = _model_set(context, template["model"]).create(rows)
        except (AccessError, MissingError, ValidationError, UserError):
            raise CapabilityError("action_rejected") from None
        record_ids = list(records.ids)
        if len(record_ids) != len(rows):
            raise CapabilityError("capability_output_invalid")
        outcome = {
            "step_id": template["step_id"],
            "model": template["model"],
            "record_ids": record_ids,
            "count": len(record_ids),
        }
        outcomes.append(outcome)
        resolved[template["step_id"]] = outcome
    return {
        "operation": "create_graph",
        "steps": outcomes,
        "total_count": sum(item["count"] for item in outcomes),
    }


def _validated_templates(context, arguments):
    if set(arguments) != {"operation", "steps"} or arguments.get("operation") != "create_graph":
        raise CapabilityError("workflow_input_invalid")
    raw_steps = arguments.get("steps")
    if not isinstance(raw_steps, list) or not 2 <= len(raw_steps) <= _MAX_WORKFLOW_STEPS:
        raise CapabilityError("workflow_steps_invalid")
    known = {}
    templates = []
    total = 0
    for raw_step in raw_steps:
        if not isinstance(raw_step, dict) or set(raw_step) != {"step_id", "model", "rows"}:
            raise CapabilityError("workflow_step_invalid")
        step_id = raw_step.get("step_id")
        if not isinstance(step_id, str) or _STEP_ID.fullmatch(step_id) is None or step_id in known:
            raise CapabilityError("workflow_step_invalid")
        model = _model_name(raw_step.get("model"))
        model_set = _model_set(context, model)
        if not _has_access(model_set, "create"):
            raise CapabilityError("access_denied")
        raw_rows = raw_step.get("rows")
        if not isinstance(raw_rows, list) or not 1 <= len(raw_rows) <= _MAX_ROWS_PER_STEP:
            raise CapabilityError("workflow_rows_invalid")
        total += len(raw_rows)
        if total > _MAX_TOTAL_ROWS:
            raise CapabilityError("workflow_rows_invalid")
        fields = set()
        for row in raw_rows:
            if not isinstance(row, dict) or not 1 <= len(row) <= 16:
                raise CapabilityError("action_values_invalid")
            for field in row:
                if not isinstance(field, str) or _FIELD.fullmatch(field) is None:
                    raise CapabilityError("action_values_invalid")
                fields.add(field)
        descriptions = _write_descriptions(context, model, tuple(sorted(fields)))
        rows = []
        for raw_row in raw_rows:
            checked = {}
            for field, value in raw_row.items():
                reference = _reference(value)
                if reference is None:
                    if isinstance(value, (dict, list)):
                        raise CapabilityError("action_value_invalid")
                    checked[field] = _validate_values(
                        context, {field: descriptions[field]}, {field: value}
                    )[field]
                    continue
                source = known.get(reference["step"])
                description = descriptions[field]
                if (
                    source is None
                    or reference["record_index"] >= source["row_count"]
                    or description.get("type") != "many2one"
                    or description.get("relation") != source["model"]
                ):
                    raise CapabilityError("workflow_reference_invalid")
                checked[field] = {"$ref": reference}
            rows.append(checked)
        template = {"step_id": step_id, "model": model, "rows": rows}
        templates.append(template)
        known[step_id] = {"model": model, "row_count": len(rows)}
    return templates


def _reference(value):
    if not isinstance(value, dict):
        return None
    if set(value) != {"$ref"} or not isinstance(value.get("$ref"), dict):
        raise CapabilityError("workflow_reference_invalid")
    reference = value["$ref"]
    if set(reference) != {"step", "record_index"}:
        raise CapabilityError("workflow_reference_invalid")
    step = reference.get("step")
    index = reference.get("record_index")
    if (
        not isinstance(step, str)
        or _STEP_ID.fullmatch(step) is None
        or type(index) is not int
        or index < 0
        or index >= _MAX_ROWS_PER_STEP
    ):
        raise CapabilityError("workflow_reference_invalid")
    return {"step": step, "record_index": index}


def _resolve_rows(context, template, resolved):
    fields = tuple(sorted({field for row in template["rows"] for field in row}))
    descriptions = _write_descriptions(context, template["model"], fields)
    rows = []
    for row in template["rows"]:
        values = {}
        for field, value in row.items():
            reference = _reference(value)
            if reference is None:
                values[field] = value
                continue
            source = resolved.get(reference["step"])
            if source is None or reference["record_index"] >= len(source["record_ids"]):
                raise CapabilityError("workflow_reference_invalid")
            values[field] = source["record_ids"][reference["record_index"]]
        rows.append(_validate_values(context, descriptions, values))
    return rows


def _workflow_result(context):
    raw = context.metadata.get("capability_result")
    if not isinstance(raw, dict) or set(raw) != {"operation", "steps", "total_count"}:
        raise CapabilityError("capability_verification_invalid")
    if raw.get("operation") != "create_graph" or not isinstance(raw.get("steps"), list):
        raise CapabilityError("capability_verification_invalid")
    if not 2 <= len(raw["steps"]) <= _MAX_WORKFLOW_STEPS:
        raise CapabilityError("capability_verification_invalid")
    total = 0
    for step in raw["steps"]:
        if not isinstance(step, dict) or set(step) != {"step_id", "model", "record_ids", "count"}:
            raise CapabilityError("capability_verification_invalid")
        record_ids = step.get("record_ids")
        if (
            not isinstance(step.get("step_id"), str)
            or not isinstance(step.get("model"), str)
            or not isinstance(record_ids, list)
            or type(step.get("count")) is not int
            or step["count"] != len(record_ids)
            or not 1 <= len(record_ids) <= _MAX_ROWS_PER_STEP
            or any(type(record_id) is not int or record_id <= 0 for record_id in record_ids)
        ):
            raise CapabilityError("capability_verification_invalid")
        total += len(record_ids)
    if raw.get("total_count") != total or total > _MAX_TOTAL_ROWS:
        raise CapabilityError("capability_verification_invalid")
    return raw


def _row_label(step_id, index, row):
    name = row.get("name")
    if isinstance(name, str) and name.strip():
        return name.strip()[:240]
    return f"{step_id} · {index + 1}"
