from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

from odoo import SUPERUSER_ID, api, fields
from odoo.exceptions import ValidationError
from odoo.modules.registry import Registry
from odoo.tests.common import TransactionCase

from ..models import turn_scheduler as scheduler_module
from ..models.turn_scheduler import (
    _TURN_CAPACITY_PARAMETER,
    _claim_next_turn,
    _effective_turn_capacity,
)


class TestAssistantTurnScheduler(TransactionCase):
    def setUp(self):
        super().setUp()
        self.dbname = self.env.cr.dbname
        with Registry(self.dbname).cursor() as cr:
            env = api.Environment(cr, SUPERUSER_ID, {}, su=True)
            record = env["ir.config_parameter"].search(
                [("key", "=", _TURN_CAPACITY_PARAMETER)], limit=1
            )
            self._previous_capacity = record.value if record else None
            env["ir.config_parameter"].set_param(_TURN_CAPACITY_PARAMETER, "2")
            cr.commit()
        self._turn_ids = []
        self._conversation_ids = []

    def tearDown(self):
        try:
            self._cleanup_seeded_records()
            with Registry(self.dbname).cursor() as cr:
                env = api.Environment(cr, SUPERUSER_ID, {}, su=True)
                record = env["ir.config_parameter"].search(
                    [("key", "=", _TURN_CAPACITY_PARAMETER)], limit=1
                )
                if self._previous_capacity is None:
                    record.unlink()
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

    def _create_turns(self, conversation_sizes):
        created = []
        with Registry(self.dbname).cursor() as cr:
            env = api.Environment(cr, SUPERUSER_ID, {}, su=True)
            admin = env.ref("base.user_admin")
            company = admin.company_id
            now = fields.Datetime.now()
            for conversation_index, size in enumerate(conversation_sizes):
                conversation = env["odoo.ai.conversation"].create(
                    {
                        "title": f"P5.2 scheduler {uuid4()}",
                        "user_id": admin.id,
                        "company_id": company.id,
                    }
                )
                self._conversation_ids.append(conversation.id)
                group = []
                for position in range(size):
                    turn = env["odoo.ai.turn"].create(
                        {
                            "turn_uuid": str(uuid4()),
                            "conversation_id": conversation.id,
                            "user_id": admin.id,
                            "company_id": company.id,
                            "state": "queued",
                            "queued_at": now
                            + timedelta(
                                seconds=(conversation_index * 20) + position
                            ),
                            "input_message": f"scheduler turn {position}",
                            "attempt_count": 0,
                            "max_attempts": 3,
                            "allowed_company_ids": [company.id],
                        }
                    )
                    self._turn_ids.append(turn.id)
                    group.append(turn.id)
                created.append(group)
            cr.commit()
        return created

    def _states(self, turn_ids):
        with Registry(self.dbname).cursor() as cr:
            env = api.Environment(cr, SUPERUSER_ID, {}, su=True)
            turns = env["odoo.ai.turn"].browse(turn_ids).exists()
            return {turn.id: turn.state for turn in turns}

    def _mark_terminal(self, turn_id):
        with Registry(self.dbname).cursor() as cr:
            env = api.Environment(cr, SUPERUSER_ID, {}, su=True)
            env["odoo.ai.turn"].browse(turn_id).write(
                {
                    "state": "completed",
                    "completed_at": fields.Datetime.now(),
                    "lease_token": False,
                    "lease_expires_at": False,
                }
            )
            cr.commit()

    def _mark_awaiting_confirmation(self, turn_id):
        with Registry(self.dbname).cursor() as cr:
            env = api.Environment(cr, SUPERUSER_ID, {}, su=True)
            env["odoo.ai.turn"].browse(turn_id).write(
                {
                    "state": "awaiting_confirmation",
                    "lease_token": False,
                    "lease_expires_at": False,
                }
            )
            cr.commit()

    def _cleanup_seeded_records(self):
        if not self._turn_ids and not self._conversation_ids:
            return
        with Registry(self.dbname).cursor() as cr:
            env = api.Environment(cr, SUPERUSER_ID, {}, su=True)
            if self._turn_ids:
                turns = env["odoo.ai.turn"].browse(self._turn_ids).exists()
                turn_uuids = turns.mapped("turn_uuid")
                if turn_uuids:
                    env["odoo.ai.turn.live.event"].search(
                        [("turn_uuid", "in", turn_uuids)]
                    ).unlink()
                turns.unlink()
            if self._conversation_ids:
                env["odoo.ai.conversation"].browse(
                    self._conversation_ids
                ).exists().unlink()
            cr.commit()

    def _repeated_claims(self, count=2):
        # TransactionCase replaces registry cursors with one lock-serialized
        # TestCursor. Repeated attempts are the deterministic contract here; the
        # real two-cron browser gates own independent-connection race coverage.
        return [_claim_next_turn(self.dbname) for _index in range(count)]

    def test_registered_cron_method_uses_p5_scheduler_overlay(self):
        with (
            patch.object(scheduler_module, "_recover_stale_turns") as recover,
            patch.object(scheduler_module, "_claim_next_turn", return_value=None) as claim,
        ):
            self.env["odoo.ai.turn"]._cron_run_turn_slot()

        recover.assert_called_once_with(self.dbname)
        claim.assert_called_once_with(self.dbname)

    def test_capacity_one_allows_only_one_of_two_repeated_claim_attempts(self):
        self._set_capacity(1)
        groups = self._create_turns([1, 1])

        results = self._repeated_claims()

        claimed = [result for result in results if result is not None]
        self.assertEqual(len(claimed), 1)
        states = self._states(groups[0] + groups[1])
        self.assertEqual(list(states.values()).count("running"), 1)
        self.assertEqual(list(states.values()).count("queued"), 1)

    def test_one_queued_turn_is_never_double_claimed_by_repeated_attempts(self):
        self._set_capacity(2)
        only_turn = self._create_turns([1])[0][0]

        results = self._repeated_claims()

        claimed = [result for result in results if result is not None]
        self.assertEqual(len(claimed), 1)
        self.assertEqual(claimed[0][0], only_turn)
        self.assertEqual(self._states([only_turn])[only_turn], "running")

    def test_event_failure_after_claim_does_not_orphan_dispatch(self):
        only_turn = self._create_turns([1])[0][0]
        event_model_type = type(self.env["odoo.ai.turn.event"])

        with patch.object(
            event_model_type,
            "append_for_turn",
            side_effect=ValidationError("injected event failure"),
        ):
            claimed = _claim_next_turn(self.dbname)

        self.assertIsNotNone(claimed)
        self.assertEqual(claimed[0], only_turn)
        self.assertEqual(self._states([only_turn])[only_turn], "running")

    def test_event_failure_does_not_rollback_stale_recovery(self):
        only_turn = self._create_turns([1])[0][0]
        claimed = _claim_next_turn(self.dbname)
        self.assertEqual(claimed[0], only_turn)
        with Registry(self.dbname).cursor() as cr:
            env = api.Environment(cr, SUPERUSER_ID, {}, su=True)
            env["odoo.ai.turn"].browse(only_turn).write(
                {"lease_expires_at": fields.Datetime.now() - timedelta(seconds=1)}
            )
            cr.commit()

        event_model_type = type(self.env["odoo.ai.turn.event"])
        with patch.object(
            event_model_type,
            "append_for_turn",
            side_effect=ValidationError("injected event failure"),
        ):
            scheduler_module._recover_stale_turns(self.dbname)

        self.assertEqual(self._states([only_turn])[only_turn], "queued")

    def test_capacity_two_allows_independent_conversations(self):
        self._set_capacity(2)
        groups = self._create_turns([1, 1])

        first = _claim_next_turn(self.dbname)
        second = _claim_next_turn(self.dbname)

        self.assertIsNotNone(first)
        self.assertIsNotNone(second)
        self.assertNotEqual(first[0], second[0])
        states = self._states(groups[0] + groups[1])
        self.assertEqual(list(states.values()).count("running"), 2)

    def test_same_conversation_preserves_creation_order_even_after_requeue_timestamp(self):
        self._set_capacity(2)
        first_id, second_id = self._create_turns([2])[0]
        with Registry(self.dbname).cursor() as cr:
            env = api.Environment(cr, SUPERUSER_ID, {}, su=True)
            first = env["odoo.ai.turn"].browse(first_id)
            second = env["odoo.ai.turn"].browse(second_id)
            first.write({"queued_at": second.queued_at + timedelta(minutes=5)})
            cr.commit()

        first_claim = _claim_next_turn(self.dbname)
        blocked_claim = _claim_next_turn(self.dbname)

        self.assertEqual(first_claim[0], first_id)
        self.assertIsNone(blocked_claim)
        self._mark_terminal(first_id)
        second_claim = _claim_next_turn(self.dbname)
        self.assertEqual(second_claim[0], second_id)

    def test_awaiting_confirmation_blocks_later_turn_without_consuming_global_slot(self):
        self._set_capacity(2)
        same_conversation = self._create_turns([2])[0]
        independent = self._create_turns([1])[0][0]

        first_claim = _claim_next_turn(self.dbname)
        self.assertEqual(first_claim[0], same_conversation[0])
        self._mark_awaiting_confirmation(same_conversation[0])

        next_claim = _claim_next_turn(self.dbname)
        self.assertEqual(next_claim[0], independent)
        states = self._states(same_conversation)
        self.assertEqual(states[same_conversation[1]], "queued")

    def test_effective_capacity_clamps_invalid_host_configuration(self):
        with Registry(self.dbname).cursor() as cr:
            env = api.Environment(cr, SUPERUSER_ID, {}, su=True)
            env["ir.config_parameter"].set_param(_TURN_CAPACITY_PARAMETER, "0")
            self.assertEqual(_effective_turn_capacity(env), 1)
            env["ir.config_parameter"].set_param(_TURN_CAPACITY_PARAMETER, "99")
            self.assertEqual(_effective_turn_capacity(env), 2)
            env["ir.config_parameter"].set_param(_TURN_CAPACITY_PARAMETER, "invalid")
            self.assertEqual(_effective_turn_capacity(env), 2)
