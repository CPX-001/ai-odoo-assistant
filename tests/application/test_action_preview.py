import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from odoo_ai.application.action_policy import (
    ACTION_POLICY_REVISION,
    action_payload_fingerprint,
)
from odoo_ai.application.action_preview import (
    ActionCreatePreviewService,
    ActionPreviewError,
    ActionPreviewService,
    BusinessActionPreviewService,
)
from odoo_ai.contracts import (
    ActionCreatePreview,
    ActionCreatePreviewSummary,
    ActionCreatePreviewValue,
    ActionCreateTarget,
    ActionFieldChange,
    ActionPreview,
    ActionPreviewChange,
    ActionPreviewSummary,
    ActionProposalPayload,
    ActionTarget,
    ActionValue,
    ActionValueKind,
    BusinessActionPreview,
    BusinessActionPreviewSummary,
    BusinessActionProposalPayload,
    EffectiveWriteFieldSchema,
    EffectiveWriteSchema,
    Evidence,
    EvidenceKind,
    EvidenceStatus,
    RecordCreateProposalPayload,
)

NOW = datetime(2026, 8, 23, 12, 0, tzinfo=UTC)
PROPOSAL_ID = UUID("11111111-1111-4111-8111-111111111111")
TURN_ID = UUID("22222222-2222-4222-8222-222222222222")
PREVIEW_ID = UUID("33333333-3333-4333-8333-333333333333")
SCHEMA_ID = "action-schema:v1:sha256:" + "a" * 64
PRECONDITION = "action-precondition:v1:sha256:" + "b" * 64


def _payload(*, value: str | None = "PO-43") -> ActionProposalPayload:
    return ActionProposalPayload(
        proposal_id=PROPOSAL_ID,
        turn_id=TURN_ID,
        instance_id="odoo-production",
        database="acme",
        uid=17,
        company_id=1,
        allowed_company_ids=(1, 3),
        target=ActionTarget(model="sale.order", record_id=42),
        changes=(
            ActionFieldChange(
                field="client_order_ref",
                value=ActionValue(kind=ActionValueKind.TEXT, value=value),
            ),
        ),
        policy_revision=ACTION_POLICY_REVISION,
        schema_revision=SCHEMA_ID,
    )


def _schema(*, required: bool = False, user: int = 17) -> EffectiveWriteSchema:
    return EffectiveWriteSchema(
        schema_id=SCHEMA_ID,
        instance_id="odoo-production",
        database="acme",
        model="sale.order",
        label="Sales Order",
        write_access=True,
        fields={
            "client_order_ref": EffectiveWriteFieldSchema(
                name="client_order_ref",
                label="Customer Reference",
                field_type="char",
                value_kind=ActionValueKind.TEXT,
                required=required,
            )
        },
        captured_for_user=user,
        company_id=1,
        allowed_company_ids=(1, 3),
        policy_revision=ACTION_POLICY_REVISION,
        captured_at=NOW,
    )


class FakePreviewGateway:
    def __init__(self, preview: ActionPreview) -> None:
        self.preview = preview
        self.preview_calls = 0
        self.mutations = 0

    async def get_write_model_metadata(self, model: str) -> Evidence:
        del model
        raise AssertionError("schema metadata is not used during preview")

    async def preview_record_patch(
        self,
        payload: ActionProposalPayload,
        *,
        payload_fingerprint: str,
    ) -> ActionPreview:
        del payload, payload_fingerprint
        self.preview_calls += 1
        return self.preview


def _preview(payload: ActionProposalPayload) -> ActionPreview:
    return ActionPreview(
        preview_id=PREVIEW_ID,
        summary=ActionPreviewSummary(
            proposal_id=payload.proposal_id,
            target=payload.target,
            changes=(
                ActionPreviewChange(
                    field="client_order_ref",
                    label="Customer Reference",
                    before=ActionValue(kind=ActionValueKind.TEXT, value="PO-42"),
                    after=payload.changes[0].value,
                ),
            ),
            warnings=("Preview only; secondary side effects are not simulated.",),
        ),
        payload_fingerprint=action_payload_fingerprint(payload),
        precondition_fingerprint=PRECONDITION,
        policy_revision=ACTION_POLICY_REVISION,
        schema_revision=SCHEMA_ID,
        observed_at=NOW,
        expires_at=NOW + timedelta(seconds=120),
    )


def test_valid_preview_produces_checked_evidence_without_mutation() -> None:
    payload = _payload()
    gateway = FakePreviewGateway(_preview(payload))

    result = asyncio.run(
        ActionPreviewService(gateway).preview(
            payload=payload,
            payload_fingerprint=action_payload_fingerprint(payload),
            schema=_schema(),
        )
    )

    assert gateway.preview_calls == 1
    assert gateway.mutations == 0
    assert result.preview.summary.changes[0].before.value == "PO-42"
    assert result.preview.summary.changes[0].after.value == "PO-43"
    assert result.evidence.kind is EvidenceKind.RECORD
    assert result.evidence.status is EvidenceStatus.CHECKED
    assert result.evidence.fingerprint == PRECONDITION
    assert set(result.evidence.payload) == {
        "expires_at",
        "observed_at",
        "payload_fingerprint",
        "policy_revision",
        "precondition_fingerprint",
        "preview_id",
        "schema_revision",
        "summary",
    }


def test_tampered_fingerprint_is_rejected_before_gateway_call() -> None:
    payload = _payload()
    gateway = FakePreviewGateway(_preview(payload))

    with pytest.raises(ActionPreviewError, match="payload_fingerprint_mismatch"):
        asyncio.run(
            ActionPreviewService(gateway).preview(
                payload=payload,
                payload_fingerprint="action-payload:v1:sha256:" + "0" * 64,
                schema=_schema(),
            )
        )

    assert gateway.preview_calls == 0


@pytest.mark.parametrize(
    "schema",
    [
        _schema(user=18),
        _schema().model_copy(update={"write_access": False, "fields": {}}),
        _schema().model_copy(update={"fields": {}}),
    ],
)
def test_schema_or_user_mismatch_fails_closed(schema: EffectiveWriteSchema) -> None:
    payload = _payload()
    gateway = FakePreviewGateway(_preview(payload))

    with pytest.raises(ActionPreviewError):
        asyncio.run(
            ActionPreviewService(gateway).preview(
                payload=payload,
                payload_fingerprint=action_payload_fingerprint(payload),
                schema=schema,
            )
        )

    assert gateway.preview_calls == 0


def test_required_null_is_rejected_before_preview() -> None:
    payload = _payload(value=None)
    gateway = FakePreviewGateway(_preview(payload))

    with pytest.raises(ActionPreviewError, match="required_value_missing"):
        asyncio.run(
            ActionPreviewService(gateway).preview(
                payload=payload,
                payload_fingerprint=action_payload_fingerprint(payload),
                schema=_schema(required=True),
            )
        )


def test_malformed_gateway_binding_is_rejected() -> None:
    payload = _payload()
    malicious = _preview(payload).model_copy(
        update={"payload_fingerprint": "action-payload:v1:sha256:" + "f" * 64}
    )

    with pytest.raises(ActionPreviewError, match="preview_binding_mismatch"):
        asyncio.run(
            ActionPreviewService(FakePreviewGateway(malicious)).preview(
                payload=payload,
                payload_fingerprint=action_payload_fingerprint(payload),
                schema=_schema(),
            )
        )


def _create_payload(*, value: str | None = "New customer") -> RecordCreateProposalPayload:
    return RecordCreateProposalPayload(
        proposal_id=PROPOSAL_ID,
        turn_id=TURN_ID,
        instance_id="odoo-production",
        database="acme",
        uid=17,
        company_id=1,
        allowed_company_ids=(1, 3),
        target=ActionCreateTarget(model="res.partner"),
        values=(
            ActionFieldChange(
                field="name",
                value=ActionValue(kind=ActionValueKind.TEXT, value=value),
            ),
        ),
        policy_revision=ACTION_POLICY_REVISION,
        schema_revision=SCHEMA_ID,
    )


def _create_schema(*, access: bool = True) -> EffectiveWriteSchema:
    field = EffectiveWriteFieldSchema(
        name="name",
        label="Name",
        field_type="char",
        value_kind=ActionValueKind.TEXT,
        required=True,
    )
    return EffectiveWriteSchema(
        schema_id=SCHEMA_ID,
        instance_id="odoo-production",
        database="acme",
        model="res.partner",
        label="Contact",
        write_access=False,
        fields={},
        create_access=access,
        create_fields={"name": field} if access else {},
        captured_for_user=17,
        company_id=1,
        allowed_company_ids=(1, 3),
        policy_revision=ACTION_POLICY_REVISION,
        captured_at=NOW,
    )


class FakeCreatePreviewGateway(FakePreviewGateway):
    def __init__(self, preview: ActionCreatePreview) -> None:
        self.create_preview = preview
        self.preview_calls = 0
        self.mutations = 0

    async def preview_record_create(
        self,
        payload: RecordCreateProposalPayload,
        *,
        payload_fingerprint: str,
    ) -> ActionCreatePreview:
        del payload, payload_fingerprint
        self.preview_calls += 1
        return self.create_preview


def _create_preview(payload: RecordCreateProposalPayload) -> ActionCreatePreview:
    return ActionCreatePreview(
        preview_id=PREVIEW_ID,
        summary=ActionCreatePreviewSummary(
            proposal_id=payload.proposal_id,
            target=payload.target,
            values=(
                ActionCreatePreviewValue(field="name", label="Name", value=payload.values[0].value),
            ),
            warnings=("Requested values only; defaults are verified after create.",),
        ),
        payload_fingerprint=action_payload_fingerprint(payload),
        precondition_fingerprint=PRECONDITION,
        policy_revision=ACTION_POLICY_REVISION,
        schema_revision=SCHEMA_ID,
        observed_at=NOW,
        expires_at=NOW + timedelta(seconds=120),
    )


def test_create_preview_is_checked_and_effect_free() -> None:
    payload = _create_payload()
    gateway = FakeCreatePreviewGateway(_create_preview(payload))

    result = asyncio.run(
        ActionCreatePreviewService(gateway).preview(
            payload=payload,
            payload_fingerprint=action_payload_fingerprint(payload),
            schema=_create_schema(),
        )
    )

    assert gateway.preview_calls == 1
    assert gateway.mutations == 0
    assert result.preview.summary.values[0].value.value == "New customer"
    assert result.evidence.status is EvidenceStatus.CHECKED
    assert "record_id" not in result.evidence.pointer


@pytest.mark.parametrize(
    "schema",
    [
        _create_schema(access=False),
        _create_schema().model_copy(update={"create_fields": {}}),
        _create_schema().model_copy(update={"captured_for_user": 18}),
    ],
)
def test_create_preview_fails_closed_for_acl_field_or_actor_mismatch(
    schema: EffectiveWriteSchema,
) -> None:
    payload = _create_payload()
    gateway = FakeCreatePreviewGateway(_create_preview(payload))

    with pytest.raises(ActionPreviewError):
        asyncio.run(
            ActionCreatePreviewService(gateway).preview(
                payload=payload,
                payload_fingerprint=action_payload_fingerprint(payload),
                schema=schema,
            )
        )

    assert gateway.preview_calls == 0


def test_create_preview_rejects_required_null_and_tampered_result() -> None:
    null_payload = _create_payload(value=None)
    with pytest.raises(ActionPreviewError, match="required_value_missing"):
        asyncio.run(
            ActionCreatePreviewService(
                FakeCreatePreviewGateway(_create_preview(null_payload))
            ).preview(
                payload=null_payload,
                payload_fingerprint=action_payload_fingerprint(null_payload),
                schema=_create_schema(),
            )
        )

    payload = _create_payload()
    malicious = _create_preview(payload).model_copy(
        update={"payload_fingerprint": "action-payload:v1:sha256:" + "f" * 64}
    )
    with pytest.raises(ActionPreviewError, match="preview_binding_mismatch"):
        asyncio.run(
            ActionCreatePreviewService(FakeCreatePreviewGateway(malicious)).preview(
                payload=payload,
                payload_fingerprint=action_payload_fingerprint(payload),
                schema=_create_schema(),
            )
        )


def _business_payload() -> BusinessActionProposalPayload:
    return BusinessActionProposalPayload(
        proposal_id=PROPOSAL_ID,
        turn_id=TURN_ID,
        instance_id="odoo-production",
        database="acme",
        uid=17,
        company_id=1,
        allowed_company_ids=(1, 3),
        target=ActionTarget(model="sale.order", record_id=42),
        policy_revision=ACTION_POLICY_REVISION,
    )


def _business_preview(payload: BusinessActionProposalPayload) -> BusinessActionPreview:
    return BusinessActionPreview(
        preview_id=PREVIEW_ID,
        summary=BusinessActionPreviewSummary(
            proposal_id=payload.proposal_id,
            action_id=payload.action_id,
            target=payload.target,
            display_name="S00042",
            state_before="draft",
            warnings=("Installed modules may add side effects.",),
        ),
        action_id=payload.action_id,
        payload_fingerprint=action_payload_fingerprint(payload),
        precondition_fingerprint=PRECONDITION,
        policy_revision=payload.policy_revision,
        action_spec_revision=payload.action_spec_revision,
        observed_at=NOW,
        expires_at=NOW + timedelta(seconds=120),
    )


class FakeBusinessPreviewGateway(FakePreviewGateway):
    def __init__(self, preview: BusinessActionPreview) -> None:
        self.business_preview = preview
        self.preview_calls = 0
        self.mutations = 0

    async def preview_business_action(
        self,
        payload: BusinessActionProposalPayload,
        *,
        payload_fingerprint: str,
    ) -> BusinessActionPreview:
        del payload, payload_fingerprint
        self.preview_calls += 1
        return self.business_preview


def test_business_action_preview_is_checked_effect_free_and_exactly_bound() -> None:
    payload = _business_payload()
    gateway = FakeBusinessPreviewGateway(_business_preview(payload))

    result = asyncio.run(
        BusinessActionPreviewService(gateway).preview(
            payload=payload,
            payload_fingerprint=action_payload_fingerprint(payload),
        )
    )

    assert gateway.preview_calls == 1
    assert gateway.mutations == 0
    assert result.preview.summary.state_before == "draft"
    assert result.preview.summary.expected_states == ("sale", "done")
    assert result.evidence.status is EvidenceStatus.CHECKED
    assert result.evidence.pointer["action_id"] == "sale.order.confirm.v1"

    malicious = _business_preview(payload).model_copy(
        update={"payload_fingerprint": "action-payload:v1:sha256:" + "f" * 64}
    )
    with pytest.raises(ActionPreviewError, match="preview_binding_mismatch"):
        asyncio.run(
            BusinessActionPreviewService(FakeBusinessPreviewGateway(malicious)).preview(
                payload=payload,
                payload_fingerprint=action_payload_fingerprint(payload),
            )
        )
