"""Odoo integration checks for persisted Phase 2 terminal failure envelopes."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

from odoo import SUPERUSER_ID, api, fields
from odoo.modules.registry import Registry
from odoo.tests.common import TransactionCase

from ..models.turn_control import _control_for_turn
from ..models.turn_failure import _fail_claimed_turn_with_failure
from ..runtime.agent.failure import FailureEnvelope


class _ProviderError(RuntimeError):
    def __init__(self, failure):
        super().__init__(failure.code)
        self.code = failure.code
        self.failure = failure


class TestAssistantTurnFailurePersistence(TransactionCase):
    def _create_running_turn(
        self,
        *,
        lease_token,
        write_barrier=False,
        attempt_count=3,
        max_attempts=3,
    ):
        dbname = self.env.cr.dbname
        with Registry(dbname).cursor() as cr:
            env = api.Environment(cr, SUPERUSER_ID, {}, su=True)
            admin = env.ref("base.user_admin")
            turn = env["odoo.ai.turn"].create(
                {
                    "turn_uuid": str(uuid4()),
                    "user_id": admin.id,
                    "company_id": admin.company_id.id,
                    "state": "running",
                    "input_message": "Prueba de failure envelope",
                    "queued_at": fields.Datetime.now(),
                    "started_at": fields.Datetime.now(),
                    "heartbeat_at": fields.Datetime.now(),
                    "lease_expires_at": fields.Datetime.now() + timedelta(minutes=5),
                    "lease_token": lease_token,
                    "attempt_count": attempt_count,
                    "max_attempts": max_attempts,
                    "write_barrier": write_barrier,
                    "allowed_company_ids": [admin.company_id.id],
                }
            )
            turn_id = turn.id
            cr.commit()
        return turn_id

    def _cleanup_turn(self, turn_id):
        dbname = self.env.cr.dbname
        with Registry(dbname).cursor() as cr:
            env = api.Environment(cr, SUPERUSER_ID, {}, su=True)
            turn = env["odoo.ai.turn"].browse(turn_id).exists()
            if turn:
                turn.unlink()
            cr.commit()

    def test_provider_failure_is_persisted_and_projected_with_legacy_code(self):
        dbname = self.env.cr.dbname
        turn_id = self._create_running_turn(lease_token="p2-terminal-provider")
        try:
            failure = FailureEnvelope(
                code="codex_turn_failed",
                category="provider_capacity",
                stage="provider",
                component="codex",
                retryability="safe",
                effect_state="none",
                user_action="retry",
                safe_summary="El proveedor está temporalmente saturado.",
                safe_details={"http_status": 503, "provider_retryable": True},
                diagnostic_id="diag-p2-odoo-0001",
                provider_code="serverOverloaded",
            )
            _fail_claimed_turn_with_failure(
                dbname,
                turn_id,
                "p2-terminal-provider",
                _ProviderError(failure),
                "codex_turn_failed",
            )

            with Registry(dbname).cursor() as cr:
                env = api.Environment(cr, SUPERUSER_ID, {}, su=True)
                turn = env["odoo.ai.turn"].browse(turn_id).exists()
                self.assertEqual(turn.state, "failed")
                self.assertEqual(turn.error_code, "codex_turn_failed")
                self.assertEqual(turn.failure_payload["category"], "provider_capacity")
                self.assertEqual(turn.failure_payload["provider_code"], "serverOverloaded")
                self.assertEqual(turn.failure_payload["effect_state"], "none")

                admin_env = api.Environment(cr, turn.user_id.id, {}, su=False)
                status = admin_env["odoo.ai.turn"].status_for_current_user(turn.turn_uuid)
                self.assertEqual(status["error_code"], "codex_turn_failed")
                self.assertEqual(status["failure"], turn.failure_payload)
        finally:
            self._cleanup_turn(turn_id)

    def test_write_barrier_forces_unknown_effect_and_disables_retry_hint(self):
        dbname = self.env.cr.dbname
        turn_id = self._create_running_turn(
            lease_token="p2-terminal-barrier",
            write_barrier=True,
        )
        try:
            failure = FailureEnvelope(
                code="codex_turn_failed",
                category="provider_capacity",
                stage="provider",
                component="codex",
                retryability="safe",
                effect_state="none",
                user_action="retry",
                safe_summary="El proveedor está temporalmente saturado.",
                safe_details={"provider_retryable": True},
                diagnostic_id="diag-p2-odoo-0002",
                provider_code="serverOverloaded",
            )
            _fail_claimed_turn_with_failure(
                dbname,
                turn_id,
                "p2-terminal-barrier",
                _ProviderError(failure),
                "codex_turn_failed",
            )

            with Registry(dbname).cursor() as cr:
                env = api.Environment(cr, SUPERUSER_ID, {}, su=True)
                turn = env["odoo.ai.turn"].browse(turn_id).exists()
                self.assertEqual(turn.state, "recovery_required")
                self.assertEqual(turn.failure_payload["effect_state"], "unknown")
                self.assertEqual(turn.failure_payload["retryability"], "never")
                self.assertEqual(turn.failure_payload["user_action"], "review")
        finally:
            self._cleanup_turn(turn_id)

    def test_usage_limit_is_terminal_without_automatic_retry(self):
        dbname = self.env.cr.dbname
        turn_id = self._create_running_turn(
            lease_token="p2-usage-limit",
            attempt_count=1,
            max_attempts=3,
        )
        try:
            failure = FailureEnvelope(
                code="codex_turn_failed",
                category="provider_capacity",
                stage="provider",
                component="codex",
                retryability="after_change",
                effect_state="none",
                user_action="retry",
                safe_summary="El proveedor alcanzó un límite de uso.",
                safe_details={},
                diagnostic_id="diag-p2-usage-limit-01",
                provider_code="usageLimitExceeded",
            )
            with patch(
                "odoo.addons.odoo_ai_assistant.models.turn_failure._trigger_turn_crons"
            ) as trigger:
                _fail_claimed_turn_with_failure(
                    dbname,
                    turn_id,
                    "p2-usage-limit",
                    _ProviderError(failure),
                    "codex_turn_failed",
                )

            with Registry(dbname).cursor() as cr:
                env = api.Environment(cr, SUPERUSER_ID, {}, su=True)
                turn = env["odoo.ai.turn"].browse(turn_id).exists()
                self.assertEqual(turn.state, "failed")
                self.assertEqual(turn.attempt_count, 1)
                self.assertEqual(turn.failure_payload["provider_code"], "usageLimitExceeded")
                trigger.assert_not_called()
        finally:
            self._cleanup_turn(turn_id)

    def test_independent_control_cancellation_settles_provider_failure_as_cancelled(self):
        dbname = self.env.cr.dbname
        turn_id = self._create_running_turn(lease_token="p7-independent-cancel")
        try:
            with Registry(dbname).cursor() as cr:
                env = api.Environment(cr, SUPERUSER_ID, {}, su=True)
                turn = env["odoo.ai.turn"].browse(turn_id)
                control = _control_for_turn(env, turn, create=True)
                control.write(
                    {
                        "cancel_requested": True,
                        "cancel_requested_at": fields.Datetime.now(),
                    }
                )
                cr.commit()

            failure = FailureEnvelope(
                code="agent_cancelled",
                category="cancellation",
                stage="cancellation",
                component="codex",
                retryability="never",
                effect_state="none",
                user_action="none",
                safe_summary="La petición fue cancelada.",
                safe_details={},
                diagnostic_id="diag-p7-cancel-control",
                provider_code=None,
            )
            _fail_claimed_turn_with_failure(
                dbname,
                turn_id,
                "p7-independent-cancel",
                _ProviderError(failure),
                "agent_cancelled",
            )

            with Registry(dbname).cursor() as cr:
                env = api.Environment(cr, SUPERUSER_ID, {}, su=True)
                turn = env["odoo.ai.turn"].browse(turn_id)
                self.assertEqual(turn.state, "cancelled")
                self.assertFalse(turn.error_code)
                self.assertFalse(turn.failure_payload)
                event = env["odoo.ai.turn.event"].search(
                    [("turn_id", "=", turn_id)], order="sequence desc", limit=1
                )
                self.assertEqual(event.event_type, "cancelled")
        finally:
            self._cleanup_turn(turn_id)

    def test_explicitly_safe_overload_can_requeue_before_write_barrier(self):
        dbname = self.env.cr.dbname
        turn_id = self._create_running_turn(
            lease_token="p2-safe-overload",
            attempt_count=1,
            max_attempts=3,
        )
        try:
            failure = FailureEnvelope(
                code="codex_turn_failed",
                category="provider_capacity",
                stage="provider",
                component="codex",
                retryability="safe",
                effect_state="none",
                user_action="retry",
                safe_summary="El proveedor está temporalmente saturado.",
                safe_details={"provider_retryable": True},
                diagnostic_id="diag-p2-safe-overload-01",
                provider_code="serverOverloaded",
            )
            with patch(
                "odoo.addons.odoo_ai_assistant.models.turn_failure._trigger_turn_crons"
            ) as trigger:
                _fail_claimed_turn_with_failure(
                    dbname,
                    turn_id,
                    "p2-safe-overload",
                    _ProviderError(failure),
                    "codex_turn_failed",
                )

            with Registry(dbname).cursor() as cr:
                env = api.Environment(cr, SUPERUSER_ID, {}, su=True)
                turn = env["odoo.ai.turn"].browse(turn_id).exists()
                self.assertEqual(turn.state, "queued")
                self.assertFalse(turn.error_code)
                self.assertFalse(turn.failure_payload)
                trigger.assert_called_once_with(dbname)
        finally:
            self._cleanup_turn(turn_id)

    def test_plain_terminal_write_gets_bounded_fallback_envelope(self):
        admin = self.env.ref("base.user_admin")
        turn = self.env["odoo.ai.turn"].with_user(SUPERUSER_ID).create(
            {
                "turn_uuid": str(uuid4()),
                "user_id": admin.id,
                "company_id": admin.company_id.id,
                "state": "running",
                "queued_at": fields.Datetime.now(),
                "attempt_count": 1,
                "max_attempts": 3,
                "allowed_company_ids": [admin.company_id.id],
            }
        )
        turn.write({"state": "failed", "error_code": "access_denied"})
        turn.invalidate_recordset()

        self.assertEqual(turn.failure_payload["category"], "odoo_access")
        self.assertEqual(turn.failure_payload["effect_state"], "none")
        self.assertEqual(turn.failure_payload["user_action"], "request_access")
