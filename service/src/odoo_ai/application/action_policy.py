"""Canonical ACTION payload hashing and conservative record-patch policy."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Final

from odoo_ai.contracts.action import (
    MAX_ACTION_FIELDS,
    ActionKind,
    ActionProposalPayload,
    ActionValueKind,
)

MAX_ACTION_PAYLOAD_BYTES: Final = 8 * 1024
ACTION_POLICY_REVISION: Final = "m6-record-patch-v1"

_BLOCKED_MODELS = frozenset(
    {
        "base.automation",
        "ir.config_parameter",
        "ir.cron",
        "ir.model",
        "ir.model.access",
        "ir.model.fields",
        "ir.rule",
        "res.groups",
        "res.users",
    }
)
_BLOCKED_MODEL_PREFIXES = ("auth.", "ir.actions.", "ir.ui.")
_BLOCKED_FIELDS = frozenset(
    {
        "__last_update",
        "company_id",
        "company_ids",
        "create_date",
        "create_uid",
        "groups_id",
        "id",
        "password",
        "password_crypt",
        "share",
        "write_date",
        "write_uid",
    }
)
_SENSITIVE_FIELD_PARTS = ("api_key", "credential", "password", "secret", "token")
_ALLOWED_VALUE_KINDS = frozenset(ActionValueKind)


class ActionPolicyError(ValueError):
    """Fail-closed policy rejection with a sanitized stable code."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def canonical_action_payload_bytes(payload: ActionProposalPayload) -> bytes:
    """Serialize validated security fields exactly once and deterministically."""

    body = payload.model_dump(mode="json")
    body["allowed_company_ids"] = sorted(body["allowed_company_ids"])
    body["changes"] = sorted(body["changes"], key=lambda change: change["field"])
    try:
        return json.dumps(
            body,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError):
        raise ActionPolicyError("invalid_payload") from None


def action_payload_fingerprint(payload: ActionProposalPayload) -> str:
    """Hash the canonical payload using an explicitly versioned domain."""

    digest = hashlib.sha256(canonical_action_payload_bytes(payload)).hexdigest()
    return f"action-payload:v{payload.format_version}:sha256:{digest}"


@dataclass(frozen=True, slots=True)
class ActionPolicy:
    """Small product policy layered on top of Odoo's authoritative permissions."""

    revision: str = ACTION_POLICY_REVISION
    max_fields: int = MAX_ACTION_FIELDS
    max_payload_bytes: int = MAX_ACTION_PAYLOAD_BYTES
    allowed_value_kinds: frozenset[ActionValueKind] = _ALLOWED_VALUE_KINDS
    allowed_models: frozenset[str] | None = None
    allowed_fields: frozenset[str] | None = None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.revision, str)
            or not 1 <= len(self.revision) <= 128
            or type(self.max_fields) is not int
            or not 1 <= self.max_fields <= MAX_ACTION_FIELDS
            or type(self.max_payload_bytes) is not int
            or not 1 <= self.max_payload_bytes <= MAX_ACTION_PAYLOAD_BYTES
            or not self.allowed_value_kinds
        ):
            raise ActionPolicyError("invalid_policy")

    def permits_model(self, model: str) -> bool:
        return (
            model not in _BLOCKED_MODELS
            and not model.startswith(_BLOCKED_MODEL_PREFIXES)
            and (self.allowed_models is None or model in self.allowed_models)
        )

    def permits_field(self, field: str) -> bool:
        normalized = field.casefold()
        return (
            field not in _BLOCKED_FIELDS
            and not any(part in normalized for part in _SENSITIVE_FIELD_PARTS)
            and (self.allowed_fields is None or field in self.allowed_fields)
        )

    def validate_payload(self, payload: ActionProposalPayload) -> None:
        if payload.action_kind is not ActionKind.RECORD_PATCH:
            raise ActionPolicyError("unsupported_action_kind")
        if payload.policy_revision != self.revision:
            raise ActionPolicyError("policy_revision_mismatch")
        if not self.permits_model(payload.target.model):
            raise ActionPolicyError("model_denied")
        if len(payload.changes) > self.max_fields:
            raise ActionPolicyError("field_limit_exceeded")
        for change in payload.changes:
            if not self.permits_field(change.field):
                raise ActionPolicyError("field_denied")
            if change.value.kind not in self.allowed_value_kinds:
                raise ActionPolicyError("value_kind_denied")
        if len(canonical_action_payload_bytes(payload)) > self.max_payload_bytes:
            raise ActionPolicyError("payload_too_large")
