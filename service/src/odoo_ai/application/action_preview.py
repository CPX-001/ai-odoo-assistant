"""Effect-free ACTION preview orchestration and checked Evidence production."""

from __future__ import annotations

import hmac
from dataclasses import dataclass
from typing import cast

from odoo_ai.application.action_policy import (
    ActionPolicy,
    ActionPolicyError,
    action_payload_fingerprint,
)
from odoo_ai.contracts import (
    ActionPreview,
    ActionProposalPayload,
    EffectiveWriteFieldSchema,
    EffectiveWriteSchema,
    Evidence,
    EvidenceKind,
    EvidenceSensitivity,
    EvidenceStatus,
)
from odoo_ai.ports.odoo import OdooActionPreviewGateway

type JsonValue = str | int | float | bool | list[JsonValue] | dict[str, JsonValue] | None


class ActionPreviewError(RuntimeError):
    """Sanitized preview rejection."""

    def __init__(self, code: str, status_code: int = 422) -> None:
        super().__init__(code)
        self.code = code
        self.status_code = status_code


@dataclass(frozen=True, slots=True)
class ActionPreviewResult:
    preview: ActionPreview
    evidence: Evidence


class ActionPreviewService:
    """Revalidate one proposal and obtain an exact diff without mutation."""

    def __init__(
        self,
        gateway: OdooActionPreviewGateway,
        *,
        policy: ActionPolicy | None = None,
    ) -> None:
        self._gateway = gateway
        self._policy = policy or ActionPolicy()

    async def preview(
        self,
        *,
        payload: ActionProposalPayload,
        payload_fingerprint: str,
        schema: EffectiveWriteSchema,
    ) -> ActionPreviewResult:
        try:
            self._policy.validate_payload(payload)
        except ActionPolicyError as error:
            raise ActionPreviewError(error.code) from None
        expected_fingerprint = action_payload_fingerprint(payload)
        if not hmac.compare_digest(payload_fingerprint, expected_fingerprint):
            raise ActionPreviewError("payload_fingerprint_mismatch", 403)
        _validate_schema_binding(payload, schema)

        preview = await self._gateway.preview_record_patch(
            payload, payload_fingerprint=expected_fingerprint
        )
        _validate_preview_binding(payload, expected_fingerprint, schema, preview)
        evidence = Evidence(
            evidence_id=preview.preview_id,
            kind=EvidenceKind.RECORD,
            status=EvidenceStatus.CHECKED,
            title=f"ACTION preview: {payload.target.model}#{payload.target.record_id}",
            summary="Current values and the proposed bounded patch were checked without mutation.",
            payload=cast(dict[str, JsonValue], preview.model_dump(mode="json")),
            pointer={
                "model": payload.target.model,
                "record_id": payload.target.record_id,
                "proposal_id": str(payload.proposal_id),
                "provider": "odoo_action_preview",
            },
            observed_at=preview.observed_at,
            sensitivity=EvidenceSensitivity.NORMAL,
            fingerprint=preview.precondition_fingerprint,
        )
        return ActionPreviewResult(preview=preview, evidence=evidence)


def _validate_schema_binding(payload: ActionProposalPayload, schema: EffectiveWriteSchema) -> None:
    if (
        not schema.write_access
        or schema.schema_id != payload.schema_revision
        or schema.policy_revision != payload.policy_revision
        or schema.model != payload.target.model
        or schema.instance_id != payload.instance_id
        or schema.database != payload.database
        or schema.captured_for_user != payload.uid
        or schema.company_id != payload.company_id
        or schema.allowed_company_ids != payload.allowed_company_ids
    ):
        raise ActionPreviewError("write_schema_mismatch", 403)
    for change in payload.changes:
        field = schema.fields.get(change.field)
        if field is None:
            raise ActionPreviewError("field_not_write_eligible", 403)
        _validate_value_for_field(change.value.kind, change.value.value, field)


def _validate_value_for_field(
    kind: object, value: object, field: EffectiveWriteFieldSchema
) -> None:
    if kind is not field.value_kind:
        raise ActionPreviewError("value_kind_mismatch")
    if field.required and (value is None or (field.value_kind.value == "text" and value == "")):
        raise ActionPreviewError("required_value_missing")
    if value is not None and field.selection is not None and value not in field.selection:
        raise ActionPreviewError("selection_value_invalid")


def _validate_preview_binding(
    payload: ActionProposalPayload,
    fingerprint: str,
    schema: EffectiveWriteSchema,
    preview: ActionPreview,
) -> None:
    if (
        preview.summary.proposal_id != payload.proposal_id
        or preview.summary.target != payload.target
        or not hmac.compare_digest(preview.payload_fingerprint, fingerprint)
        or preview.policy_revision != payload.policy_revision
        or preview.schema_revision != schema.schema_id
    ):
        raise ActionPreviewError("preview_binding_mismatch", 502)
    expected_changes = {change.field: change.value for change in payload.changes}
    observed_changes = {change.field: change.after for change in preview.summary.changes}
    if (
        len(observed_changes) != len(preview.summary.changes)
        or observed_changes != expected_changes
    ):
        raise ActionPreviewError("preview_binding_mismatch", 502)
