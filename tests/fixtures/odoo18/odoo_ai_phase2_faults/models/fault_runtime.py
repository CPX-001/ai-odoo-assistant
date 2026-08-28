"""Test-only deterministic Phase 2 failures through the real Odoo turn queue.

This addon lives under tests/fixtures and injects nothing unless both the explicit
process environment flag and the disposable-database prefix are present.
"""

from __future__ import annotations

import os

from odoo import SUPERUSER_ID, api, fields, models
from odoo.exceptions import AccessError, ValidationError
from odoo.modules.registry import Registry

from odoo.addons.odoo_ai_assistant.models.embedded_runtime import EmbeddedRuntimeError
from odoo.addons.odoo_ai_assistant.runtime.agent.failure import FailureEnvelope
from odoo.addons.odoo_ai_assistant.runtime.agent.provider_failure import ProviderFailureError

_FIXTURE_FLAG = "ODOO_AI_PHASE2_FAULT_FIXTURE"
_DISPOSABLE_DB_PREFIX = "odoo_ai_"

FAULT_AUTH = "__P2_REAL_AUTH__"
FAULT_ACL = "__P2_REAL_ACL__"
FAULT_TIMEOUT = "__P2_REAL_TIMEOUT__"
FAULT_TOOLFAIL = "__P2_REAL_TOOLFAIL__"
FAULT_RECOVERY = "__P2_REAL_RECOVERY__"
FAULT_MESSAGES = frozenset(
    {FAULT_AUTH, FAULT_ACL, FAULT_TIMEOUT, FAULT_TOOLFAIL, FAULT_RECOVERY}
)


class Phase2Secret(models.Model):
    _name = "odoo.ai.phase2.secret"
    _description = "Phase 2 Restricted Test Record"

    name = fields.Char(required=True)


class Phase2FaultRuntime(models.AbstractModel):
    _inherit = "odoo.ai.embedded.runtime"

    @api.model
    def run_turn(self, *, turn_id, lease_token):
        turn = self._phase2_bound_turn(turn_id=turn_id, lease_token=lease_token)
        marker = (turn.input_message or "").strip()
        if not _fixture_enabled(self.env) or marker not in FAULT_MESSAGES:
            return super().run_turn(turn_id=turn_id, lease_token=lease_token)

        # Make the injected fault terminal on its current claim so a real-gate run does
        # not wait through ordinary transient retry attempts.
        _force_current_claim_terminal(self.env.cr.dbname, turn.id, turn.attempt_count)

        if marker == FAULT_AUTH:
            raise ProviderFailureError(
                _provider_failure(
                    code="codex_turn_failed",
                    category="authentication",
                    retryability="after_change",
                    user_action="reconnect",
                    provider_code="unauthorized",
                    safe_summary="Fallo de autenticación controlado por el fixture de Phase 2.",
                    detail="p2-auth-private-detail",
                )
            )
        if marker == FAULT_ACL:
            # The fixture record is readable only by base.group_system. The real turn
            # still runs under the originating user Environment with su=False.
            records = self.env["odoo.ai.phase2.secret"].search([], limit=1)
            records.read(["name"])
            raise EmbeddedRuntimeError("phase2_acl_fixture_unexpected_access")
        if marker == FAULT_TIMEOUT:
            raise ProviderFailureError(
                _provider_failure(
                    code="engine_timeout",
                    category="provider_connection",
                    retryability="safe",
                    user_action="retry",
                    provider_code=None,
                    safe_summary="Timeout controlado antes de cualquier efecto de negocio.",
                    detail="p2-timeout-private-detail",
                )
            )
        if marker == FAULT_TOOLFAIL:
            raise EmbeddedRuntimeError("capability_execution_failed")
        if marker == FAULT_RECOVERY:
            _persist_write_barrier(self.env.cr.dbname, turn.id)
            raise EmbeddedRuntimeError("worker_lost_after_write_barrier")
        raise EmbeddedRuntimeError("phase2_fault_fixture_invalid")

    def _phase2_bound_turn(self, *, turn_id, lease_token):
        if self.env.su:
            raise AccessError("Phase 2 fixture cannot run in superuser mode")
        if type(turn_id) is not int or turn_id <= 0 or not isinstance(lease_token, str):
            raise ValidationError("Invalid Phase 2 fixture turn binding")
        turn = self.env["odoo.ai.turn"].browse(turn_id).exists()
        if (
            not turn
            or turn.user_id.id != self.env.uid
            or turn.company_id.id != self.env.company.id
            or turn.state != "running"
            or turn.lease_token != lease_token
        ):
            raise AccessError("Phase 2 fixture turn binding is no longer valid")
        return turn


def _fixture_enabled(env):
    return (
        os.environ.get(_FIXTURE_FLAG) == "1"
        and env.cr.dbname.startswith(_DISPOSABLE_DB_PREFIX)
    )


def _provider_failure(
    *,
    code,
    category,
    retryability,
    user_action,
    provider_code,
    safe_summary,
    detail,
):
    return FailureEnvelope(
        code=code,
        category=category,
        stage="provider",
        component="codex",
        retryability=retryability,
        effect_state="none",
        user_action=user_action,
        safe_summary=safe_summary,
        safe_details={"fixture_detail": detail},
        diagnostic_id=f"diag-p2real-{category}",
        provider_code=provider_code,
    )


def _force_current_claim_terminal(dbname, turn_id, attempt_count):
    with Registry(dbname).cursor() as cr:
        env = api.Environment(cr, SUPERUSER_ID, {}, su=True)
        turn = env["odoo.ai.turn"].browse(turn_id).exists()
        if not turn:
            raise EmbeddedRuntimeError("phase2_fault_fixture_turn_missing")
        turn.write({"max_attempts": max(1, int(attempt_count or 1))})
        cr.commit()


def _persist_write_barrier(dbname, turn_id):
    with Registry(dbname).cursor() as cr:
        env = api.Environment(cr, SUPERUSER_ID, {}, su=True)
        turn = env["odoo.ai.turn"].browse(turn_id).exists()
        if not turn:
            raise EmbeddedRuntimeError("phase2_fault_fixture_turn_missing")
        turn.write({"write_barrier": True, "heartbeat_at": fields.Datetime.now()})
        cr.commit()
