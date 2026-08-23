"""Private Odoo-side idempotency receipts for irreversible M6 effects."""

from datetime import UTC, datetime
from typing import ClassVar, Final
from uuid import UUID

from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError
from psycopg2 import IntegrityError

_INTERNAL_MARKER: Final = object()
_INTERNAL_CONTEXT: Final = "_odoo_ai_action_execution_internal"
_ACTION_KINDS: Final = (
    ("business_action", "Business action"),
    ("record_create", "Record create"),
)


class ActionExecutionReceipt(models.Model):
    """Store an effect result atomically with the Odoo transaction that produced it."""

    _name = "odoo.ai.action.execution"
    _description = "Odoo AI Action Execution Receipt"
    _order = "expires_at, id"

    jti = fields.Char(required=True, index=True, readonly=True)
    attempt_id = fields.Char(required=True, index=True, readonly=True)
    proposal_id = fields.Char(required=True, index=True, readonly=True)
    action_kind = fields.Selection(_ACTION_KINDS, required=True, readonly=True)
    payload_fingerprint = fields.Char(required=True, index=True, readonly=True)
    target_model = fields.Char(required=True, readonly=True)
    target_record_id = fields.Integer(readonly=True)
    status = fields.Selection(
        (("pending", "Pending"), ("completed", "Completed")),
        required=True,
        readonly=True,
    )
    expires_at = fields.Datetime(required=True, index=True, readonly=True)

    _sql_constraints: ClassVar = [
        (
            "odoo_ai_action_execution_jti_unique",
            "unique(jti)",
            "This action authority has already been used.",
        ),
        (
            "odoo_ai_action_execution_attempt_unique",
            "unique(attempt_id)",
            "This action attempt already has a receipt.",
        ),
    ]

    def _internal(self):
        return self.with_context(**{_INTERNAL_CONTEXT: _INTERNAL_MARKER})

    def _require_internal(self):
        if self.env.context.get(_INTERNAL_CONTEXT) is not _INTERNAL_MARKER:
            raise AccessError("Action execution receipts are internal only.")

    @api.model_create_multi
    def create(self, vals_list):
        self._require_internal()
        return super().create(vals_list)

    def write(self, vals):
        self._require_internal()
        return super().write(vals)

    def unlink(self):
        self._require_internal()
        return super().unlink()

    @api.model
    def search(self, domain, offset=0, limit=None, order=None):
        self._require_internal()
        return super().search(domain, offset=offset, limit=limit, order=order)

    def read(self, fields=None, load="_classic_read"):
        self._require_internal()
        return super().read(fields=fields, load=load)

    @api.model
    def _claim(
        self,
        *,
        jti: str,
        attempt_id: UUID,
        proposal_id: UUID,
        action_kind: str,
        payload_fingerprint: str,
        target_model: str,
        expires_at: int,
    ):
        """Return `(receipt, is_new)`; an existing matching attempt is recoverable."""

        values = _validated_values(
            jti=jti,
            attempt_id=attempt_id,
            proposal_id=proposal_id,
            action_kind=action_kind,
            payload_fingerprint=payload_fingerprint,
            target_model=target_model,
            expires_at=expires_at,
        )
        internal = self._internal()
        existing = internal.search([("attempt_id", "=", values["attempt_id"])], limit=1)
        if existing:
            _require_receipt_binding(existing, values)
            return existing, False
        try:
            with self.env.cr.savepoint():
                receipt = internal.create({**values, "status": "pending"})
        except IntegrityError:
            receipt = internal.search(
                [("attempt_id", "=", values["attempt_id"])], limit=1
            )
            if not receipt:
                raise ValidationError("Action receipt conflict.") from None
            _require_receipt_binding(receipt, values)
            return receipt, False
        return receipt, True

    def _complete(self, *, record_id: int):
        self._require_internal()
        if len(self) != 1 or type(record_id) is not int or record_id <= 0:
            raise ValidationError("Invalid action receipt result.")
        if self.status == "completed":
            if self.target_record_id != record_id:
                raise ValidationError("Action receipt result mismatch.")
            return self
        if self.status != "pending" or self.target_record_id:
            raise ValidationError("Invalid action receipt state.")
        self.write({"status": "completed", "target_record_id": record_id})
        return self

    @api.model
    def _get_completed(
        self,
        *,
        attempt_id: UUID,
        proposal_id: UUID,
        action_kind: str,
        payload_fingerprint: str,
        target_model: str,
    ):
        expected = _validated_values(
            jti="verify_0123456789abcdefghi",
            attempt_id=attempt_id,
            proposal_id=proposal_id,
            action_kind=action_kind,
            payload_fingerprint=payload_fingerprint,
            target_model=target_model,
            expires_at=1,
        )
        receipt = self._internal().search(
            [("attempt_id", "=", expected["attempt_id"])], limit=1
        )
        if not receipt:
            return receipt
        _require_receipt_binding(receipt, expected)
        if receipt.status != "completed" or receipt.target_record_id <= 0:
            raise ValidationError("Action receipt is not complete.")
        return receipt

    @api.autovacuum
    def _gc_expired_action_receipts(self):
        self._internal().search([("expires_at", "<", fields.Datetime.now())]).unlink()


def _validated_values(**values):
    if (
        not isinstance(values["jti"], str)
        or not 22 <= len(values["jti"]) <= 64
        or not isinstance(values["attempt_id"], UUID)
        or not isinstance(values["proposal_id"], UUID)
        or values["action_kind"] not in dict(_ACTION_KINDS)
        or not isinstance(values["payload_fingerprint"], str)
        or not values["payload_fingerprint"].startswith("action-payload:v1:sha256:")
        or len(values["payload_fingerprint"]) != 89
        or not isinstance(values["target_model"], str)
        or not 1 <= len(values["target_model"]) <= 128
        or type(values["expires_at"]) is not int
        or values["expires_at"] <= 0
    ):
        raise ValidationError("Invalid action receipt values.")
    return {
        "jti": values["jti"],
        "attempt_id": str(values["attempt_id"]),
        "proposal_id": str(values["proposal_id"]),
        "action_kind": values["action_kind"],
        "payload_fingerprint": values["payload_fingerprint"],
        "target_model": values["target_model"],
        "expires_at": datetime.fromtimestamp(values["expires_at"], UTC).replace(
            tzinfo=None
        ),
    }


def _require_receipt_binding(receipt, expected):
    if (
        receipt.proposal_id != expected["proposal_id"]
        or receipt.action_kind != expected["action_kind"]
        or receipt.payload_fingerprint != expected["payload_fingerprint"]
        or receipt.target_model != expected["target_model"]
    ):
        raise ValidationError("Action receipt binding mismatch.")
