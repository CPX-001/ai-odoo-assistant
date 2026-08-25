import ast
import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from uuid import UUID

import pytest
from odoo_ai.application import (
    EffectiveSchemaError,
    EffectiveSchemaPolicy,
    EffectiveSchemaService,
)
from odoo_ai.contracts import (
    EffectiveModelSchema,
    Evidence,
    EvidenceKind,
    EvidenceSensitivity,
    EvidenceStatus,
    RecordRef,
    RecordSnapshot,
    export_public_json_schemas,
)
from pydantic import JsonValue

CAPTURED_AT = datetime(2026, 8, 22, 10, 30, tzinfo=UTC)
SOURCE_ROOT = Path(__file__).resolve().parents[2] / "service" / "src" / "odoo_ai"


class FakeGateway:
    def __init__(self, evidence: Evidence) -> None:
        self.evidence = evidence
        self.requested_models: list[str] = []

    async def get_model_metadata(self, model: str) -> Evidence:
        self.requested_models.append(model)
        return self.evidence

    async def read_records(
        self, records: list[RecordRef], fields: list[str]
    ) -> list[RecordSnapshot]:
        raise AssertionError("M5-01 must not execute record queries")


def _field(
    field_type: str,
    *,
    label: str = "Field",
    relation: str | None = None,
    selection: list[list[str]] | None = None,
    searchable: bool = True,
    sortable: bool = True,
    groupable: bool = True,
) -> dict[str, JsonValue]:
    result: dict[str, JsonValue] = {
        "groupable": groupable,
        "readonly": False,
        "required": False,
        "searchable": searchable,
        "sortable": sortable,
        "string": label,
        "type": field_type,
    }
    if relation is not None:
        result["relation"] = relation
    if selection is not None:
        result["selection"] = cast(JsonValue, selection)
    return result


def _metadata(
    fields: dict[str, dict[str, JsonValue]],
    *,
    model: str = "sale.order",
) -> Evidence:
    return Evidence(
        evidence_id=UUID("12345678-1234-5678-1234-567812345678"),
        kind=EvidenceKind.METADATA,
        status=EvidenceStatus.CHECKED,
        title="Odoo model metadata",
        summary="Delegated fields_get result.",
        payload={
            "fields": cast(JsonValue, fields),
            "label": "Sales Order",
            "model": model,
        },
        pointer={"model": model, "provider": "odoo_http"},
        observed_at=CAPTURED_AT,
        sensitivity=EvidenceSensitivity.TECHNICAL,
    )


def _run(
    metadata: Evidence,
    *,
    policy: EffectiveSchemaPolicy | None = None,
) -> tuple[FakeGateway, EffectiveModelSchema, Evidence]:
    gateway = FakeGateway(metadata)
    result = asyncio.run(
        EffectiveSchemaService(gateway, policy=policy).get(
            model="sale.order", captured_for_user=17
        )
    )
    return gateway, result.schema, result.evidence


def test_effective_schema_contains_only_visible_runtime_fields_and_checked_evidence() -> (
    None
):
    gateway, schema, evidence = _run(
        _metadata(
            {
                "partner_id": _field(
                    "many2one", label="Customer", relation="res.partner"
                ),
                "state": _field(
                    "selection",
                    label="Status",
                    selection=[["draft", "Quotation"], ["sale", "Sales Order"]],
                ),
            }
        )
    )

    assert gateway.requested_models == ["sale.order"]
    assert tuple(schema.fields) == ("partner_id", "state")
    assert "restricted_margin" not in schema.fields
    assert schema.fields["partner_id"].relation == "res.partner"
    assert [option.value for option in schema.fields["state"].selection or ()] == [
        "draft",
        "sale",
    ]
    assert schema.captured_for_user == 17
    assert evidence.kind is EvidenceKind.METADATA
    assert evidence.status is EvidenceStatus.CHECKED
    assert evidence.pointer == {
        "model": "sale.order",
        "provider": "effective_schema",
        "schema_id": schema.schema_id,
    }
    assert evidence.fingerprint == schema.revision
    assert evidence.payload["fields"] == json.loads(schema.model_dump_json())["fields"]


def test_odoo_capabilities_are_narrowed_by_policy_and_fingerprint_is_reproducible() -> (
    None
):
    metadata = _metadata(
        {
            "amount_total": _field("float"),
            "notes": _field("text", sortable=True, groupable=True),
        }
    )

    _, first, _ = _run(metadata)
    _, second, _ = _run(metadata)

    assert first.fields["amount_total"].searchable is True
    assert first.fields["amount_total"].sortable is True
    assert first.fields["amount_total"].groupable is False
    assert first.fields["notes"].searchable is True
    assert first.fields["notes"].sortable is False
    assert first.fields["notes"].groupable is False
    assert first.schema_id == second.schema_id


@pytest.mark.parametrize(
    "fields",
    [
        {"name": {"type": "char"}},
        {"line_ids": _field("one2many")},
        {"binary_data": _field("binary")},
        {
            "state": _field(
                "selection",
                selection=[["draft", "Draft"], ["draft", "Duplicate"]],
            )
        },
        {"name": {**_field("char"), "relation": "res.partner"}},
    ],
)
def test_inconsistent_or_unsupported_metadata_fails_closed(
    fields: dict[str, dict[str, JsonValue]],
) -> None:
    with pytest.raises(EffectiveSchemaError) as failure:
        _run(_metadata(fields))

    assert failure.value.code in {"invalid_metadata", "unsupported_metadata"}


def test_effective_schema_enforces_field_and_byte_caps() -> None:
    with pytest.raises(EffectiveSchemaError, match="invalid_metadata"):
        _run(
            _metadata({"name": _field("char"), "state": _field("char")}),
            policy=EffectiveSchemaPolicy(max_fields=1),
        )

    with pytest.raises(EffectiveSchemaError, match="schema_too_large"):
        _run(
            _metadata({"name": _field("char", label="x" * 256)}),
            policy=EffectiveSchemaPolicy(max_bytes=256),
        )


def test_effective_schema_public_json_schema_is_reproducible() -> None:
    first = export_public_json_schemas()
    second = export_public_json_schemas()

    assert first["EffectiveModelSchema"] == second["EffectiveModelSchema"]
    assert first["EffectiveFieldSchema"] == second["EffectiveFieldSchema"]
    assert first["EffectiveSelectionOption"] == second["EffectiveSelectionOption"]


def test_effective_schema_application_has_no_odoo_adapter_or_version_imports() -> None:
    source_path = SOURCE_ROOT / "application" / "effective_schema.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    }

    assert not any(name == "odoo" or name.startswith("odoo.") for name in imported)
    assert not any(name.startswith("odoo_ai.adapters") for name in imported)
    assert "odoo_version" not in source_path.read_text(encoding="utf-8")
