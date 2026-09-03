"""P5.2 host-owned scheduler admission, fairness, wake-up and diagnostics."""

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
    _trigger_turn_crons,
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

    # Updated on every scheduler claim, including retries. ``started_at`` is the
    # first-start timestamp and therefore cannot act as a fair service watermark.
    scheduler_claimed_at = fields.Datetime(readonly=True, index=True)

    @api.model
    def _cron_run_turn_slot(self):
        """Run one bounded slot and wake pending work after the slot returns."""

        dbname = self.env.cr.dbname
        _recover_stale_turns(dbname)
        claimed = _claim_next_turn(dbname)
        if not claimed:
            return
        turn_id, lease_token = claimed
        try:
            _execute_claimed_turn(dbname, turn_id, lease_token)
        except Exception as error:
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
        finally:
            # Completion/failure/cancellation/approval-pause all release or re-evaluate
            # capacity after their authoritative transaction. A fresh claim always
            # rechecks capacity, so an unusual early return cannot over-admit work.
            _wake_turn_crons_safely(dbname)

    @api.model
    def cancel_for_current_user(self, turn_uuid):
        """Wake a successor after cancelling a queued causal predecessor."""

        turn = self._owned_turn(turn_uuid)
        was_queued = turn.state == "queued"
        result = super().cancel_for_current_user(turn_uuid)
        if was_queued and result.get("state") == "cancelled":
            _schedule_postcommit_wake(self.env.cr)
        return result

    @api.model
    def decide_capability_plan_for_current_user(self, plan_id, decision):
        """Wake only after an approval decision becomes transactionally visible."""

        result = super().decide_capability_plan_for_current_user(plan_id, decision)
        if result.get("state") in {"authorized", "rejected"}:
            _schedule_postcommit_wake(self.env.cr)
        return result


class AssistantSchedulerDiagnostics(models.TransientModel):
    _inherit = "odoo.ai.assistant.diagnostics"

    scheduler_capacity = fields.Char(
        string="Current capacity",
        readonly=True,
        help=(
            "Shows how many Assistant requests are running now, the installation "
            "limit and the remaining free slots."
        ),
    )
    scheduler_queue = fields.Char(
        string="Waiting requests",
        readonly=True,
        help=(
            "Summarizes requests waiting to run, ready to start, blocked by "
            "conversation order or awaiting approval."
        ),
    )
    scheduler_wait = fields.Char(
        string="Queue wait",
        readonly=True,
        help=(
            "Shows how long the oldest request has waited and how many users currently "
            "have queued or active work."
        ),
    )

    def _diagnostic_values(self):
        values = super()._diagnostic_values()
        snapshot = _scheduler_snapshot(self.env)
        values.update(
            scheduler_capacity=(
                f"{snapshot['active_count']}/{snapshot['effective_capacity']} active "
                f"({snapshot['available_slots']} free)"
            ),
            scheduler_queue=(
                f"{snapshot['queued_count']} queued; {snapshot['eligible_count']} eligible; "
                f"{snapshot['causally_blocked_count']} causally blocked; "
                f"{snapshot['awaiting_confirmation_count']} awaiting approval"
            ),
            scheduler_wait=(
                f"oldest queued: {snapshot['oldest_queue_wait_seconds']}s; "
                f"queued users: {snapshot['queued_user_count']}; "
                f"active users: {snapshot['active_user_count']}"
            ),
        )
        return values

    @api.model
    def assistant_scheduler_snapshot(self):
        """Administrator-only bounded scheduler telemetry for diagnostics/real gates."""

        self._require_admin()
        return _scheduler_snapshot(self.env)


def _configured_turn_capacity(env):
    raw = env["ir.config_parameter"]._get_param(_TURN_CAPACITY_PARAMETER)
    if raw in (None, False, ""):
        return _DEFAULT_TURN_CAPACITY
    try:
        return int(str(raw).strip())
    except (TypeError, ValueError):
        return None


def _effective_turn_capacity(env):
    """Resolve the safe host ceiling for future claims."""

    configured = _configured_turn_capacity(env)
    if configured is None:
        configured = _DEFAULT_TURN_CAPACITY
    return max(1, min(configured, _SUPPORTED_RUNNER_CAPACITY))


def _prepare_claim_transaction(cr):
    """Use READ COMMITTED for real claim cursors before their first snapshot.

    Odoo's TransactionCase registry replaces newly requested cursors with a `TestCursor`
    backed by the already-active test transaction. PostgreSQL cannot change isolation
    after that transaction has executed queries, and the test cursor itself serializes
    access to the shared transaction. We therefore leave the test transaction untouched;
    true multi-connection race behavior is covered by the P5.2 real cron/browser gates.

    Production Registry cursors are fresh here, so changing isolation is the first SQL
    statement and guarantees an advisory-lock waiter sees the previous claim commit.
    """

    cursor_type = type(cr)
    if cursor_type.__name__ == "TestCursor" and cursor_type.__module__.startswith(
        "odoo.tests."
    ):
        return
    cr.execute("SET TRANSACTION ISOLATION LEVEL READ COMMITTED")


def _claim_next_turn(dbname):
    """Claim one eligible turn under bounded capacity and anti-starvation ordering.

    Odoo production cursors use PostgreSQL REPEATABLE READ by default. This short
    scheduler transaction switches to READ COMMITTED before taking the advisory lock so
    a worker that waited for another claim sees the previous claim's committed state.

    Fairness order is ``fewest active turns for user -> least recently claimed user ->
    FIFO``. Conversation causality is stronger than fairness: an earlier non-terminal
    predecessor always blocks a later turn in the same conversation.
    """

    with Registry(dbname).cursor() as cr:
        _prepare_claim_transaction(cr)
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
              LEFT JOIN LATERAL (
                    SELECT
                        COUNT(*) FILTER (
                            WHERE peer.state IN ('running', 'cancel_requested')
                        ) AS active_count,
                        MAX(peer.scheduler_claimed_at) AS last_claimed_at
                      FROM odoo_ai_turn AS peer
                     WHERE peer.user_id = candidate.user_id
              ) AS service ON TRUE
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
             ORDER BY
                   service.active_count ASC,
                   service.last_claimed_at ASC NULLS FIRST,
                   candidate.queued_at ASC,
                   candidate.id ASC
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
                   scheduler_claimed_at = %s,
                   heartbeat_at = %s,
                   lease_expires_at = %s,
                   lease_token = %s,
                   write_date = %s
             WHERE id = %s
            """,
            [now, now, now, expires_at, lease_token, now, turn_id],
        )
        cr.commit()

    _append_event(dbname, turn_id, "started", "Procesando petición")
    return turn_id, lease_token


def _scheduler_snapshot(env):
    """Return aggregate host facts only; never prompt/provider-private data."""

    effective_capacity = _effective_turn_capacity(env)
    configured_capacity = _configured_turn_capacity(env)
    cr = env.cr
    cr.execute(
        """
        SELECT
            COUNT(*) FILTER (
                WHERE state IN ('running', 'cancel_requested')
            ) AS active_count,
            COUNT(*) FILTER (
                WHERE state = 'queued' AND attempt_count < max_attempts
            ) AS queued_count,
            COUNT(*) FILTER (
                WHERE state = 'awaiting_confirmation'
            ) AS awaiting_confirmation_count,
            COUNT(DISTINCT user_id) FILTER (
                WHERE state = 'queued' AND attempt_count < max_attempts
            ) AS queued_user_count,
            COUNT(DISTINCT user_id) FILTER (
                WHERE state IN ('running', 'cancel_requested')
            ) AS active_user_count,
            MIN(queued_at) FILTER (
                WHERE state = 'queued' AND attempt_count < max_attempts
            ) AS oldest_queued_at
          FROM odoo_ai_turn
        """
    )
    (
        active_count,
        queued_count,
        awaiting_confirmation_count,
        queued_user_count,
        active_user_count,
        oldest_queued_at,
    ) = cr.fetchone()
    cr.execute(
        """
        SELECT COUNT(*)
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
        """
    )
    eligible_count = cr.fetchone()[0]
    oldest_wait = 0
    if oldest_queued_at is not None:
        oldest_wait = max(
            0,
            int((fields.Datetime.now() - oldest_queued_at).total_seconds()),
        )
    return {
        "configured_capacity": configured_capacity,
        "effective_capacity": effective_capacity,
        "supported_runner_capacity": _SUPPORTED_RUNNER_CAPACITY,
        "active_count": int(active_count),
        "available_slots": max(0, effective_capacity - int(active_count)),
        "queued_count": int(queued_count),
        "eligible_count": int(eligible_count),
        "causally_blocked_count": max(0, int(queued_count) - int(eligible_count)),
        "awaiting_confirmation_count": int(awaiting_confirmation_count),
        "queued_user_count": int(queued_user_count),
        "active_user_count": int(active_user_count),
        "oldest_queue_wait_seconds": oldest_wait,
    }


def _schedule_postcommit_wake(cr):
    dbname = cr.dbname
    cr.postcommit.add(lambda: _wake_turn_crons_safely(dbname))


def _wake_turn_crons_safely(dbname):
    try:
        _trigger_turn_crons(dbname)
    except Exception:
        _logger.exception("Could not wake pending Assistant turns after capacity release")
