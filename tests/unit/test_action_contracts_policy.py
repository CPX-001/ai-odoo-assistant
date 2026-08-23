from uuid import UUID

import pytest
from pydantic import ValidationError

from odoo_ai.application.action_policy import (
    ACTION_POLICY_REVISION,
    ActionPolicy,
    ActionPolicyError,
    action_payload_fingerprint,
    canonical_action_payload_bytes,
)
from odoo_ai.contracts import ProposedAction
from odoo_ai.contracts.action import (
    ActionFieldChange,
    ActionProposalPayload,
    ActionTarget,
    ActionValue,
    ActionValueKind,
)

PROPOSAL_ID = UUID("11111111-1111-4111-8111-111111111111")
TURN_ID = UUID("22222222-2222-4222-8222-222222222222")


def _payload(
    *, changes: tuple[ActionFieldChange, ...] | None = None, **updates: object
):
    values: dict[str, object] = {
        "proposal_id": PROPOSAL_ID,
        "turn_id": TURN_ID,
        "instance_id": "odoo-production",
        "database": "acme",
        "uid": 17,
        "company_id": 1,
        "allowed_company_ids": (1, 3),
        "target": ActionTarget(model="sale.order", record_id=42),
        "changes": changes
        or (
            ActionFieldChange(
                field="client_order_ref",
                value=ActionValue(kind=ActionValueKind.TEXT, value="PO-42"),
            ),
        ),
        "policy_revision": ACTION_POLICY_REVISION,
        "schema_revision": "schema-42",
    }
    values.update(updates)
    return ActionProposalPayload.model_validate(values)


def test_canonical_payload_is_stable_for_change_order() -> None:
    first = ActionFieldChange(
        field="client_order_ref",
        value=ActionValue(kind=ActionValueKind.TEXT, value="PO-42"),
    )
    second = ActionFieldChange(
        field="note",
        value=ActionValue(kind=ActionValueKind.TEXT, value="safe data"),
    )

    left = _payload(changes=(first, second))
    right = _payload(changes=(second, first))

    assert canonical_action_payload_bytes(left) == canonical_action_payload_bytes(right)
    assert action_payload_fingerprint(left) == action_payload_fingerprint(right)


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("database", "other"),
        ("uid", 18),
        ("target", ActionTarget(model="sale.order", record_id=43)),
        ("target", ActionTarget(model="purchase.order", record_id=42)),
        ("schema_revision", "schema-43"),
    ],
)
def test_security_binding_changes_fingerprint(field: str, replacement: object) -> None:
    original = _payload()
    changed = _payload(**{field: replacement})

    assert action_payload_fingerprint(original) != action_payload_fingerprint(changed)


def test_field_and_value_changes_change_fingerprint() -> None:
    original = _payload()
    changed_field = _payload(
        changes=(
            ActionFieldChange(
                field="note",
                value=ActionValue(kind=ActionValueKind.TEXT, value="PO-42"),
            ),
        )
    )
    changed_value = _payload(
        changes=(
            ActionFieldChange(
                field="client_order_ref",
                value=ActionValue(kind=ActionValueKind.TEXT, value="PO-43"),
            ),
        )
    )

    assert (
        len(
            {
                action_payload_fingerprint(original),
                action_payload_fingerprint(changed_field),
                action_payload_fingerprint(changed_value),
            }
        )
        == 3
    )


def test_contracts_reject_extras_coercion_duplicates_and_unknown_kind() -> None:
    raw = _payload().model_dump(mode="json")
    with pytest.raises(ValidationError):
        ActionProposalPayload.model_validate({**raw, "method": "write"})
    with pytest.raises(ValidationError):
        ActionProposalPayload.model_validate({**raw, "uid": "17"})
    with pytest.raises(ValidationError):
        ActionProposalPayload.model_validate({**raw, "action_kind": "execute_method"})
    with pytest.raises(ValidationError):
        ActionProposalPayload.model_validate(
            {**raw, "changes": [raw["changes"][0], raw["changes"][0]]}
        )
    with pytest.raises(ValidationError):
        ActionValue.model_validate({"kind": "integer", "value": True})
    with pytest.raises(ValidationError):
        ActionValue.model_validate({"kind": "decimal", "value": "1.00"})


def test_policy_is_bounded_and_denies_sensitive_surfaces() -> None:
    ActionPolicy().validate_payload(_payload())

    with pytest.raises(ActionPolicyError, match="model_denied"):
        ActionPolicy().validate_payload(
            _payload(target=ActionTarget(model="res.users", record_id=17))
        )
    with pytest.raises(ActionPolicyError, match="field_denied"):
        ActionPolicy().validate_payload(
            _payload(
                changes=(
                    ActionFieldChange(
                        field="api_token",
                        value=ActionValue(
                            kind=ActionValueKind.TEXT, value="not-a-secret"
                        ),
                    ),
                )
            )
        )
    with pytest.raises(ActionPolicyError, match="payload_too_large"):
        ActionPolicy(max_payload_bytes=256).validate_payload(_payload())


def test_adversarial_text_stays_data_and_proposed_action_is_not_authority() -> None:
    payload = _payload(
        changes=(
            ActionFieldChange(
                field="note",
                value=ActionValue(
                    kind=ActionValueKind.TEXT,
                    value="'; DROP TABLE sale_order; __import__('os').system('id')",
                ),
            ),
        )
    )
    ActionPolicy().validate_payload(payload)
    assert b"DROP TABLE" in canonical_action_payload_bytes(payload)

    presentation = ProposedAction(action_type="record_patch", summary="Change the note")
    with pytest.raises(ValidationError):
        ActionProposalPayload.model_validate(presentation.model_dump())
