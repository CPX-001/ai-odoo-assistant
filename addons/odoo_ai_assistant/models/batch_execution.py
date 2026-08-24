"""Private Odoo-side row receipts for idempotent batch mutations."""

from datetime import timedelta
from typing import ClassVar, Final
from uuid import UUID

from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError
from psycopg2 import IntegrityError

_INTERNAL_MARKER: Final = object()
_INTERNAL_CONTEXT: Final = "_odoo_ai_batch_execution_internal"
_RECEIPT_RETENTION_DAYS: Final = 90
_OPERATIONS: Final = (
    ("create", "Create"),
    ("patch", "Patch"),
    ("delete", "Delete"),
)
_STATUSES: Final = (
    ("pending", "Pending"),
    ("applied", "Applied"),
    ("failed", "Failed"),
)


class BatchExecutionReceipt(models.Model):
    """Persist one row outcome atomically with the Odoo transaction that produced it."""

    _name = "odoo.ai.batch.execution"
    _description = "Odoo AI Batch Execution Receipt"
    _order = "expires_at, id"

    job_id = fields.Char(required=True, index=True, readonly=True)
    attempt_id = fields.Char(required=True, index=True, readonly=True)
    authorization_id = fields.Char(required=True, index=True, readonly=True)
    job_fingerprint = fields.Char(required=True, index=True, readonly=True)
    operation = fields.Selection(_OPERATIONS, required=True, readonly=True)
    target_model = fields.Char(required=True, readonly=True)
    source_ref = fields.Char(required=True, readonly=True)
    item_fingerprint = fields.Char(required=True, readonly=True)
    status = fields.Selection(_STATUSES, required=True, readonly=True)
    target_record_id = fields.Integer(readonly=True)
    error_code = fields.Char(readonly=True)
    expires_at = fields.Datetime(required=True, index=True, readonly=True)

    _sql_constraints: ClassVar = [
        (
            "odoo_ai_batch_execution_attempt_source_unique",
            "unique(attempt_id, source_ref)",
            "This batch row already has an execution receipt.",
        ),
    ]

    def _internal(self):
        return self.with_context(**{_INTERNAL_CONTEXT: _INTERNAL_MARKER})

    def _require_internal(self):
        if self.env.context.get(_INTERNAL_CONTEXT) is not _INTERNAL_MARKER:
            raise AccessError("Batch execution receipts are internal only.")

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
        job_id: UUID,
        attempt_id: UUID,
        authorization_id: UUID,
        job_fingerprint: str,
        operation: str,
        target_model: str,
        source_ref: str,
        item_fingerprint: str,
    ):
        """Return ``(receipt, is_new)`` for one immutable row identity."""

        values = _validated_values(
            job_id=job_id,
            attempt_id=attempt_id,
            authorization_id=authorization_id,
            job_fingerprint=job_fingerprint,
            operation=operation,
            target_model=target_model,
            source_ref=source_ref,
            item_fingerprint=item_fingerprint,
        )
        internal = self._internal()
        existing = internal.search(
            [
                ("attempt_id", "=", values["attempt_id"]),
                ("source_ref", "=", values["source_ref"]),
            ],
            limit=1,
        )
        if existing:
            _require_binding(existing, values)
            return existing, False
        values["expires_at"] = fields.Datetime.now() + timedelta(
            days=_RECEIPT_RETENTION_DAYS
        )
        try:
            with self.env.cr.savepoint():
                receipt = internal.create({**values, "status": "pending"})
        except IntegrityError:
            receipt = internal.search(
                [
                    ("attempt_id", "=", values["attempt_id"]),
                    ("source_ref", "=", values["source_ref"]),
                ],
                limit=1,
            )
            if not receipt:
                raise ValidationError("Batch receipt conflict.") from None
            _require_binding(receipt, values)
            return receipt, False
        return receipt, True

    def _complete_applied(self, *, record_id: int):
        self._require_internal()
        if len(self) != 1 or type(record_id) is not int or record_id <= 0:
            raise ValidationError("Invalid batch receipt result.")
        if self.status == "applied":
            if self.target_record_id != record_id or self.error_code:
                raise ValidationError("Batch receipt result mismatch.")
            return self
        if self.status != "pending" or self.target_record_id or self.error_code:
            raise ValidationError("Invalid batch receipt state.")
        self.write(
            {
                "status": "applied",
                "target_record_id": record_id,
            }
        )
        return self

    def _complete_failed(self, *, error_code: str):
        self._require_internal()
        if (
            len(self) != 1
            or not isinstance(error_code, str)
            or not 1 <= len(error_code) <= 128
            or any(not (character.islower() or character.isdigit() or character == "_") for character in error_code)
        ):
            raise ValidationError("Invalid batch receipt failure.")
        if self.status == "failed":
            if self.error_code != error_code or self.target_record_id:
                raise ValidationError("Batch receipt failure mismatch.")
            return self
        if self.status != "pending" or self.target_record_id or self.error_code:
            raise ValidationError("Invalid batch receipt state.")
        self.write({"status": "failed", "error_code": error_code})
        return self

    def _result(self):
        self._require_internal()
        if len(self) != 1 or self.status == "pending":
            raise ValidationError("Batch receipt is not complete.")
        return {
            "source_ref": self.source_ref,
            "state": "applied" if self.status == "applied" else "failed",
            "record_id": self.target_record_id if self.status == "applied" else None,
            "error_code": self.error_code if self.status == "failed" else None,
        }

    @api.autovacuum
    def _gc_expired_batch_receipts(self):
        self._internal().search([("expires_at", "<", fields.Datetime.now())]).unlink()


def _validated_values(**values):
    if (
        not isinstance(values["job_id"], UUID)
        or not isinstance(values["attempt_id"], UUID)
        or not isinstance(values["authorization_id"], UUID)
        or not isinstance(values["job_fingerprint"], str)
        or not values["job_fingerprint"].startswith("batch-job:v1:sha256:")
        or len(values["job_fingerprint"]) != 84
        or values["operation"] not in dict(_OPERATIONS)
        or not isinstance(values["target_model"], str)
        or not 1 <= len(values["target_model"]) <= 128
        or not isinstance(values["source_ref"], str)
        or not 1 <= len(values["source_ref"]) <= 128
        or values["source_ref"] != values["source_ref"].strip()
        or not isinstance(values["item_fingerprint"], str)
        or not values["item_fingerprint"].startswith("batch-item:v1:sha256:")
        or len(values["item_fingerprint"]) != 85
    ):
        raise ValidationError("Invalid batch receipt values.")
    return {
        "job_id": str(values["job_id"]),
        "attempt_id": str(values["attempt_id"]),
        "authorization_id": str(values["authorization_id"]),
        "job_fingerprint": values["job_fingerprint"],
        "operation": values["operation"],
        "target_model": values["target_model"],
        "source_ref": values["source_ref"],
        "item_fingerprint": values["item_fingerprint"],
    }


def _require_binding(receipt, expected):
    if (
        receipt.job_id != expected["job_id"]
        or receipt.authorization_id != expected["authorization_id"]
        or receipt.job_fingerprint != expected["job_fingerprint"]
        or receipt.operation != expected["operation"]
        or receipt.target_model != expected["target_model"]
        or receipt.item_fingerprint != expected["item_fingerprint"]
    ):
        raise ValidationError("Batch receipt binding mismatch.")
