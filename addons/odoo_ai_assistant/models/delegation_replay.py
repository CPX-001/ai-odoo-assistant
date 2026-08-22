"""Single-use ledger for delegated M2 read scopes."""

from datetime import UTC, datetime
from typing import ClassVar, Final

from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError
from psycopg2 import IntegrityError

_INTERNAL_CREATE_MARKER: Final = object()
_INTERNAL_CREATE_CONTEXT: Final = "_odoo_ai_delegation_use_create"
_SCOPES: Final = (
    ("aggregate_records", "Aggregate records"),
    ("fields_get", "Fields metadata"),
    ("navigation", "Navigation metadata"),
    ("query_records", "Query records"),
    ("query_schema", "Query schema"),
    ("read_records", "Read records"),
)


class DelegationUse(models.Model):
    """Record a consumed ``(jti, scope)`` without storing the signed token."""

    _name = "odoo.ai.delegation.use"
    _description = "Odoo AI Delegation Scope Use"
    _order = "expires_at, id"

    jti = fields.Char(required=True, index=True, readonly=True)
    scope = fields.Selection(_SCOPES, required=True, index=True, readonly=True)
    expires_at = fields.Datetime(required=True, index=True, readonly=True)

    _sql_constraints: ClassVar = [
        (
            "odoo_ai_delegation_jti_scope_unique",
            "unique(jti, scope)",
            "This delegation scope has already been consumed.",
        )
    ]

    @api.model_create_multi
    def create(self, vals_list):
        """Prevent normal ORM/RPC callers from writing the internal ledger."""

        if (
            self.env.context.get(_INTERNAL_CREATE_CONTEXT)
            is not _INTERNAL_CREATE_MARKER
        ):
            raise AccessError("Delegation ledger writes are internal only.")
        return super().create(vals_list)

    @api.model
    def _consume(self, *, jti: str, scope: str, expires_at: int) -> bool:
        """Atomically consume one signed scope; return ``False`` on replay."""

        if (
            not isinstance(jti, str)
            or not 22 <= len(jti) <= 64
            or scope not in dict(_SCOPES)
            or type(expires_at) is not int
            or expires_at <= 0
        ):
            raise ValidationError("Invalid delegation ledger values.")
        expiration = datetime.fromtimestamp(expires_at, UTC).replace(tzinfo=None)
        try:
            with self.env.cr.savepoint():
                self.with_context(
                    **{_INTERNAL_CREATE_CONTEXT: _INTERNAL_CREATE_MARKER}
                ).create(
                    {
                        "expires_at": expiration,
                        "jti": jti,
                        "scope": scope,
                    }
                )
        except IntegrityError:
            return False
        return True

    @api.autovacuum
    def _gc_expired_delegation_uses(self):
        """Keep only still-relevant technical nonce records."""

        self.search([("expires_at", "<", fields.Datetime.now())]).unlink()
