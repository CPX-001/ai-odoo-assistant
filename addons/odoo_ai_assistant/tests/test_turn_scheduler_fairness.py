from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from odoo import SUPERUSER_ID, Command, api, fields
from odoo.exceptions import AccessError
from odoo.modules.registry import Registry
from odoo.tests.common import TransactionCase

from ..models import turn_scheduler as scheduler_module
from ..models.turn_scheduler import (
    _TURN_CAPACITY_PARAMETER,
    _claim_next_turn,
    _scheduler_snapshot,
)


class _CallbackCollector:
    def __init__(self):
        self.callbacks = []

    def add(self, callback):
        self.callbacks.append(callback)


class TestAssistantTurnSchedulerFairness(TransactionCase):
    def setUp(self):
        super().setUp()
        self.dbname = self.env.cr.dbname
        self._turn_ids = []
        self._conversation_ids = []
        self._user_ids = []
        with Registry(self.dbname).cursor() as cr:
            env = api.Environment(cr, SUPERUSER_ID, {}, su=True)
            parameter = env["ir.config_parameter"].search(
                [("key", "=", _TURN_CAPACITY_PARAMETER)], limit=1
            )
            self._previous_capacity = parameter.value if parameter else None
            env["ir.config_parameter"].set_param(_TURN_CAPACITY_PARAMETER, "2")
            company = env.company
            group = env.ref("base.group_user")
            users = []
            for label in ("A", "B"):
                user = env["res.users"].create(
                    {
                        "name": f"P5.2 Fairness User {label}",
                        "login": f"p52-fair-{label.lower()}-{uuid4()}",
                        "company_id": company.id,
                        "company_ids": [Command.set([company.id])],
                        "groups_id": [Command.set([group.id])],
                    }
                )
                self._user_ids.append(user.id)
                users.append(user.id)
            self.user_a_id, self.user_b_id = users
            cr.commit()

    def tearDown(self):
        try:
            with Registry(self.dbname).cursor() as cr:
                env = api.Environment(cr, SUPERUSER_ID, {}, su=True)
                if self._turn_ids:
                    env["odoo.ai.turn"].browse(self._turn_ids).exists().unlink()
                if self._conversation_ids:
                    env["odoo.ai.conversation"].browse(
                        self._conversation_ids
                    ).exists().unlink()
                if self._user_ids:
                    env["res.users"].browse(self._user_ids).exists().unlink()
                parameter = env["ir.config_parameter"].search(
                    [("key", "=", _TURN_CAPACITY_PARAMETER)], limit=1
                )
                if self._previous_capacity is None:
                    parameter.unlink()
                else:
                    env["ir.config_parameter"].set_param(
                        _TURN_CAPACITY_PARAMETER, self._previous_capacity
                    )
                cr.commit()
        finally:
            super().tearDown()

    def _set_capacity(self, value):
        with Registry(self.dbname).cursor() as cr:
            env = api.Environment(cr, SUPERUSER_ID, {}, su=True)
            env["ir.config_parameter"].set_param(_TURN_CAPACITY_PARAMETER, str(value))
            cr.commit()

    def _new_conversation(self, user_id):
        with Registry(self.dbname).cursor() as cr:
            env = api.Environment(cr, SUPERUSER_ID, {}, su=True)
            user = env["res.users"].browse(user_id)
            conversation = env["odoo.ai.conversation"].create(
                {
                    "title": f"P5.2 fairness {uuid4()}",
                    "user_id": user.id,
                    "company_id": user.company_id.id,
                }
            )
            self._conversation_ids.append(conversation.id)
            cr.commit()
            return conversation.id

    def _new_turn(self, user_id, *, age_seconds, conversation_id=None):
        if conversation_id is None:
            conversation_id = self._new_conversation(user_id)
        with Registry(self.dbname).cursor() as cr:
            env = api.Environment(cr, SUPERUSER_ID, {}, su=True)
            user = env["res.users"].browse(user_id)
            turn = env["odoo.ai.turn"].create(
                {
                    "turn_uuid": str(uuid4()),
                    "conversation_id": conversation_id,
                    "user_id": user.id,
                    "company_id": user.company_id.id,
                    "state": "queued",
                    "queued_at": fields.Datetime.now() - timedelta(seconds=age_seconds),
                    "input_message": "P5.2 scheduler fairness",
                    "attempt_count": 0,
                    "max_attempts": 3,
                    "allowed_company_ids": [user.company_id.id],
                }
            )
            self._turn_ids.append(turn.id)
            cr.commit()
            return turn.id

    def _mark(self, turn_id, state):
        with Registry(self.dbname).cursor() as cr:
            env = api.Environment(cr, SUPERUSER_ID, {}, su=True)
            values = {
                "state": state,
                "lease_token": False,
                "lease_expires_at": False,
            }
            if state in {"completed", "failed", "cancelled", "recovery_required"}:
                values["completed_at"] = fields.Datetime.now()
            env["odoo.ai.turn"].browse(turn_id).write(values)
            cr.commit()

    def test_capacity_one_rotates_to_waiting_user_instead_of_old_fifo_backlog(self):
        self._set_capacity(1)
        first_a = self._new_turn(self.user_a_id, age_seconds=40)
        second_a = self._new_turn(self.user_a_id, age_seconds=30)
        first_b = self._new_turn(self.user_b_id, age_seconds=10)

        self.assertEqual(_claim_next_turn(self.dbname)[0], first_a)
        self._mark(first_a, "completed")

        # B is newer than A's remaining backlog, but A was just served. The scheduler
        # must rotate to the least-recently-served waiting user rather than pure FIFO.
        self.assertEqual(_claim_next_turn(self.dbname)[0], first_b)
        with Registry(self.dbname).cursor() as cr:
            env = api.Environment(cr, SUPERUSER_ID, {}, su=True)
            self.assertEqual(env["odoo.ai.turn"].browse(second_a).state, "queued")

    def test_zero_active_user_gets_spare_slot_before_second_backlog_turn(self):
        self._set_capacity(2)
        first_a = self._new_turn(self.user_a_id, age_seconds=40)
        second_a = self._new_turn(self.user_a_id, age_seconds=30)
        first_b = self._new_turn(self.user_b_id, age_seconds=10)

        self.assertEqual(_claim_next_turn(self.dbname)[0], first_a)
        self.assertEqual(_claim_next_turn(self.dbname)[0], first_b)
        with Registry(self.dbname).cursor() as cr:
            env = api.Environment(cr, SUPERUSER_ID, {}, su=True)
            self.assertEqual(env["odoo.ai.turn"].browse(second_a).state, "queued")

    def test_retry_requeue_does_not_restore_old_fifo_priority(self):
        self._set_capacity(1)
        turn_a = self._new_turn(self.user_a_id, age_seconds=60)
        turn_b = self._new_turn(self.user_b_id, age_seconds=10)
        self.assertEqual(_claim_next_turn(self.dbname)[0], turn_a)

        with Registry(self.dbname).cursor() as cr:
            env = api.Environment(cr, SUPERUSER_ID, {}, su=True)
            env["odoo.ai.turn"].browse(turn_a).write(
                {
                    "state": "queued",
                    "queued_at": fields.Datetime.now() - timedelta(minutes=5),
                    "lease_token": False,
                    "lease_expires_at": False,
                }
            )
            cr.commit()

        self.assertEqual(_claim_next_turn(self.dbname)[0], turn_b)

    def test_capacity_change_only_controls_future_claims(self):
        self._set_capacity(1)
        first = self._new_turn(self.user_a_id, age_seconds=20)
        second = self._new_turn(self.user_b_id, age_seconds=10)
        self.assertEqual(_claim_next_turn(self.dbname)[0], first)
        self.assertIsNone(_claim_next_turn(self.dbname))

        self._set_capacity(2)
        self.assertEqual(_claim_next_turn(self.dbname)[0], second)

    def test_recovery_required_predecessor_is_terminal_for_scheduler(self):
        conversation_id = self._new_conversation(self.user_a_id)
        first = self._new_turn(
            self.user_a_id, age_seconds=20, conversation_id=conversation_id
        )
        second = self._new_turn(
            self.user_a_id, age_seconds=10, conversation_id=conversation_id
        )
        self._mark(first, "recovery_required")

        self.assertEqual(_claim_next_turn(self.dbname)[0], second)

    def test_worker_release_wakes_pending_scheduler(self):
        with (
            patch.object(scheduler_module, "_recover_stale_turns"),
            patch.object(
                scheduler_module, "_claim_next_turn", return_value=(999, "lease")
            ),
            patch.object(scheduler_module, "_execute_claimed_turn"),
            patch.object(scheduler_module, "_trigger_turn_crons") as trigger,
        ):
            self.env["odoo.ai.turn"]._cron_run_turn_slot()

        trigger.assert_called_once_with(self.dbname)

    def test_queued_cancellation_registers_postcommit_wake(self):
        turn_id = self._new_turn(self.user_a_id, age_seconds=10)
        with patch.object(scheduler_module, "_schedule_postcommit_wake") as schedule:
            with Registry(self.dbname).cursor() as cr:
                env = api.Environment(cr, self.user_a_id, {}, su=False)
                turn = env["odoo.ai.turn"].browse(turn_id)
                result = env["odoo.ai.turn"].cancel_for_current_user(turn.turn_uuid)
                self.assertEqual(result["state"], "cancelled")
                schedule.assert_called_once_with(cr)
                cr.commit()

    def test_postcommit_wake_callback_defers_trigger_until_callback_runs(self):
        collector = _CallbackCollector()
        fake_cursor = SimpleNamespace(dbname=self.dbname, postcommit=collector)
        with patch.object(scheduler_module, "_trigger_turn_crons") as trigger:
            scheduler_module._schedule_postcommit_wake(fake_cursor)
            trigger.assert_not_called()
            self.assertEqual(len(collector.callbacks), 1)
            collector.callbacks[0]()
            trigger.assert_called_once_with(self.dbname)

    def test_scheduler_snapshot_is_bounded_and_reports_causal_backlog(self):
        self._set_capacity(2)
        conversation_id = self._new_conversation(self.user_a_id)
        first = self._new_turn(
            self.user_a_id, age_seconds=30, conversation_id=conversation_id
        )
        self._new_turn(self.user_a_id, age_seconds=20, conversation_id=conversation_id)
        self._new_turn(self.user_b_id, age_seconds=10)
        self.assertEqual(_claim_next_turn(self.dbname)[0], first)

        with Registry(self.dbname).cursor() as cr:
            env = api.Environment(cr, SUPERUSER_ID, {}, su=True)
            snapshot = _scheduler_snapshot(env)

        self.assertEqual(snapshot["effective_capacity"], 2)
        self.assertGreaterEqual(snapshot["active_count"], 1)
        self.assertGreaterEqual(snapshot["queued_count"], 2)
        self.assertGreaterEqual(snapshot["eligible_count"], 1)
        self.assertGreaterEqual(snapshot["causally_blocked_count"], 1)
        self.assertGreaterEqual(snapshot["oldest_queue_wait_seconds"], 0)
        self.assertNotIn("turn_id", snapshot)
        self.assertNotIn("message", snapshot)

    def test_scheduler_snapshot_requires_system_admin(self):
        with Registry(self.dbname).cursor() as cr:
            env = api.Environment(cr, self.user_a_id, {}, su=False)
            with self.assertRaises(AccessError):
                env["odoo.ai.assistant.diagnostics"].assistant_scheduler_snapshot()
