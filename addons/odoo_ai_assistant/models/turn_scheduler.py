"""P5.2 host-owned scheduler admission and causal turn claiming."""

from __future__ import annotations

import logging
import secrets
from datetime import timedelta

from odoo import SUPERUSER_ID, api, fields, models
from odoo.modules.registry import Registry

from ..runtime.agent.failure import FailureEnvelope
from .turn_failure import _fail_claimed_turn_with_failure
from .turn_queue import (
    _LEASE_SECONDS,
    _append_event,
    _execute_claimed_turn,
    _fail_claimed_turn,
    _recover_stale_turns,
    _runtime_error_code,
)

_logger = logging.getLogger(__name__)

_TURN_CAPACITY_PARAMETER = "odoo_ai_assistant.concurrent_turns"
_DEFAULT_TURN_CAPACITY = 2
_SUPPORTED_RUNNER_CAPACITY = 2
# Stable project-local PostgreSQL advisory-lock namespace. It serializes only the
# short admission/claim decision; provider/business execution never holds it.
_SCHEDULER_CLAIM_LOCK_KEY = 6_895_220_052


class AssistantTurnScheduler(models.Model):
    _inherit = "odoo.ai.turn"

    @api.model
    def _cron_run_turn_slot(self):
        """Run one bounded scheduler slot using P5.2 admission semantics."""

        dbname = self.env.cr.dbname
        _recover_stale_turns(dbname)
        claimed = _claim_next_turn(dbname)
        if not claimed:
            return
        turn_id, lease_token = claimed
        try:
            _execute_claimed_turn(dbname, turn_id, lease_token)
        except Exception as error:  # noqa: BLE001 - cron boundary stays sanitized
            code = _runtime_error_code(error)
            _logger.exception("Embedded Assistant turn %s crashed: %s", turn_id, code)
            if isinstance(getattr(error, "failure", None), FailureEnvelope):
                _fail_claimed_turn_with_failure(
                    dbname,
                    turn_id,
                    lease_token,
                    error,
                    code,
                )
            else:
                _fail_claimed_turn(dbname, turn_id, lease_token, code)


def _effective_turn_capacity(env):
    """Resolve the safe host ceiling for future claims.

    The current product has two physical cron runner slots. A manually edited invalid
    parameter therefore degrades to a safe bounded value instead of disabling the
    scheduler or claiming more concurrency than the installed runner pool can provide.
    """

    raw = env["ir.config_parameter"]._get_param(_TURN_CAPACITY_PARAMETER)
    if raw in (None, False, ""):
        configured = _DEFAULT_TURN_CAPACITY
    else:
        try:
            configured = int(str(raw).strip())
        except (TypeError, ValueError):
            configured = _DEFAULT_TURN_CAPACITY
    return max(1, min(configured, _SUPPORTED_RUNNER_CAPACITY))


def _claim_next_turn(dbname):
    """Claim one eligible turn under a race-safe installation-wide capacity ceiling.

    Admission is serialized with a transaction-scoped PostgreSQL advisory lock. The
    lock covers only capacity inspection + candidate transition to ``running``. Once
    committed, provider work proceeds concurrently in the independent cron workers.

    Causal ordering uses turn creation identity, not ``queued_at``. A retry may move an
    older turn's queue timestamp forward, but a later turn in the same conversation
    must still wait for that predecessor.
    """

    with Registry(dbname).cursor() as cr:
        env = api.Environment(cr, SUPERUSER_ID, {}, su=True)
        cr.execute("SELECT pg_advisory_xact_lock(%s)", [_SCHEDULER_CLAIM_LOCK_KEY])

        capacity = _effective_turn_capacity(env)
        cr.execute(
            """
            SELECT COUNT(*)
              FROM odoo_ai_turn
             WHERE state IN ('running', 'cancel_requested')
            """
        )
        active_count = cr.fetchone()[0]
        if active_count >= capacity:
            return None

        cr.execute(
            """
            SELECT candidate.id
              FROM odoo_ai_turn AS candidate
             WHERE candidate.state = 'queued'
               AND candidate.attempt_count < candidate.max_attempts
               AND NOT EXISTS (
                    SELECT 1
                      FROM odoo_ai_turn AS predecessor
                     WHERE predecessor.conversation_id = candidate.conversation_id
                       AND predecessor.id < candidate.id
                       AND (
                            predecessor.state IN (
                                'running',
                                'cancel_requested',
                                'awaiting_confirmation'
                            )
                            OR (
                                predecessor.state = 'queued'
                                AND predecessor.attempt_count < predecessor.max_attempts
                            )
                       )
               )
             ORDER BY candidate.queued_at, candidate.id
             FOR UPDATE OF candidate SKIP LOCKED
             LIMIT 1
            """
        )
        row = cr.fetchone()
        if not row:
            return None

        turn_id = row[0]
        lease_token = secrets.token_urlsafe(24)
        now = fields.Datetime.now()
        expires_at = now + timedelta(seconds=_LEASE_SECONDS)
        cr.execute(
            """
            UPDATE odoo_ai_turn
               SET state = 'running',
                   attempt_count = attempt_count + 1,
                   started_at = COALESCE(started_at, %s),
                   heartbeat_at = %s,
                   lease_expires_at = %s,
                   lease_token = %s,
                   write_date = %s
             WHERE id = %s
            """,
            [now, now, expires_at, lease_token, now, turn_id],
        )
        cr.commit()

    _append_event(dbname, turn_id, "started", "Procesando petición")
    return turn_id, lease_token
