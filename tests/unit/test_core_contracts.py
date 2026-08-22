import json
from datetime import UTC, datetime
from uuid import UUID

import pytest
from pydantic import ValidationError

from odoo_ai.contracts import (
    Evidence,
    EvidenceKind,
    EvidenceSensitivity,
    EvidenceStatus,
    RecordRef,
    ScreenContext,
)


def test_screen_context_constructs_and_serializes_to_json() -> None:
    context = ScreenContext(
        action_id=12,
        menu_id=34,
        view_type="form",
        model="sale.order",
        res_id=56,
        selected_ids=[56, 57],
        allowed_context_subset={"active_test": True, "search_default_my_orders": 1},
        captured_at=datetime(2026, 8, 21, 10, 30, tzinfo=UTC),
    )

    serialized = json.loads(context.model_dump_json())

    assert serialized["model"] == "sale.order"
    assert serialized["selected_ids"] == [56, 57]
    assert serialized["captured_at"] == "2026-08-21T10:30:00Z"


def test_screen_context_defaults_are_not_shared() -> None:
    captured_at = datetime(2026, 8, 21, 10, 30)  # noqa: DTZ001 - test fixture
    first = ScreenContext(captured_at=captured_at)
    second = ScreenContext(captured_at=captured_at)

    first.selected_ids.append(1)
    first.allowed_context_subset["active_test"] = False

    assert second.selected_ids == []
    assert second.allowed_context_subset == {}


def test_screen_context_rejects_browser_identity_and_non_json_context() -> None:
    captured_at = datetime(2026, 8, 21, 10, 30)  # noqa: DTZ001 - test fixture

    with pytest.raises(ValidationError):
        ScreenContext.model_validate({"captured_at": captured_at, "user_id": 7})

    with pytest.raises(ValidationError):
        ScreenContext(
            captured_at=captured_at,
            allowed_context_subset={"unsafe": object()},
        )


@pytest.mark.parametrize(
    "captured_at",
    [
        datetime(2026, 8, 21, 10, 30),  # noqa: DTZ001 - supported input
        datetime(2026, 8, 21, 10, 30, tzinfo=UTC),
    ],
)
def test_screen_context_serializes_supported_datetime_forms(captured_at: datetime) -> None:
    serialized = json.loads(ScreenContext(captured_at=captured_at).model_dump_json())

    assert isinstance(serialized["captured_at"], str)


def test_record_ref_constructs_and_serializes_to_json() -> None:
    reference = RecordRef(model="res.partner", id=42, display_name="Azure Interior")

    assert json.loads(reference.model_dump_json()) == {
        "model": "res.partner",
        "id": 42,
        "display_name": "Azure Interior",
    }


def test_evidence_constructs_and_serializes_to_json() -> None:
    evidence = Evidence(
        evidence_id=UUID("12345678-1234-5678-1234-567812345678"),
        kind=EvidenceKind.RECORD,
        status=EvidenceStatus.CHECKED,
        title="Quotation",
        summary="Quotation was read under the effective Odoo user.",
        payload={"model": "sale.order", "id": 56, "confirmed": False},
        pointer={"model": "sale.order", "res_id": 56},
        observed_at=datetime(2026, 8, 21, 10, 30, tzinfo=UTC),
        sensitivity=EvidenceSensitivity.NORMAL,
        fingerprint="sha256:example",
    )

    serialized = json.loads(evidence.model_dump_json())

    assert serialized["evidence_id"] == "12345678-1234-5678-1234-567812345678"
    assert serialized["kind"] == "record"
    assert serialized["status"] == "checked"
    assert serialized["sensitivity"] == "normal"


def test_evidence_payload_defaults_are_not_shared() -> None:
    common_values = {
        "evidence_id": UUID("12345678-1234-5678-1234-567812345678"),
        "kind": EvidenceKind.GENERAL,
        "status": EvidenceStatus.GENERAL,
        "title": "General guidance",
        "summary": "No instance-specific evidence was used.",
        "sensitivity": EvidenceSensitivity.NORMAL,
    }
    first = Evidence(**common_values)
    second = Evidence(**common_values)

    first.payload["source"] = "documentation"

    assert second.payload == {}


@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    [
        ("kind", "database"),
        ("status", "verified"),
        ("sensitivity", "secret"),
    ],
)
def test_evidence_rejects_values_outside_enums(field_name: str, invalid_value: str) -> None:
    values = {
        "evidence_id": "12345678-1234-5678-1234-567812345678",
        "kind": "record",
        "status": "checked",
        "title": "Quotation",
        "summary": "Quotation evidence.",
        "sensitivity": "normal",
    }
    values[field_name] = invalid_value

    with pytest.raises(ValidationError):
        Evidence.model_validate(values)


@pytest.mark.parametrize("contract", [ScreenContext, RecordRef, Evidence])
def test_contract_json_schema_is_serializable(contract: type[object]) -> None:
    schema = contract.model_json_schema()

    assert json.loads(json.dumps(schema))["type"] == "object"
