"""Odoo integration coverage for the Phase 4 live answer projection.

These tests do not prove real Codex streaming; they validate the independent Odoo/browser
transport used by the real Phase 4 gates.
"""
from uuid import uuid4

from odoo import SUPERUSER_ID, api
from odoo.exceptions import AccessError, ValidationError
from odoo.modules.registry import Registry
from odoo.tests.common import TransactionCase


class TestPhase4LiveProjection(TransactionCase):
    def _committed_turn(self):
        dbname = self.env.cr.dbname
        with Registry(dbname).cursor() as cr:
            env = api.Environment(cr, SUPERUSER_ID, {}, su=True)
            user = env.ref("base.user_admin")
            turn = env["odoo.ai.turn"].create(
                {
                    "turn_uuid": str(uuid4()),
                    "user_id": user.id,
                    "company_id": user.company_id.id,
                    "state": "running",
                    "input_message": "Phase 4 live projection",
                    "allowed_company_ids": [user.company_id.id],
                    "attempt_count": 1,
                    "max_attempts": 1,
                }
            )
            result = turn.id, turn.turn_uuid, user.id
            cr.commit()
            return result

    def test_unicode_answer_delta_is_visible_once_by_cursor(self):
        turn_id, turn_uuid, user_id = self._committed_turn()
        live = self.env["odoo.ai.turn.live.event"]
        live.append_answer_delta_independent(
            turn_id=turn_id,
            text="España, pingüino, acción, 😀",
        )
        browser = self.env["odoo.ai.turn"].with_user(user_id)
        first = browser.live_for_current_user(turn_uuid, after_sequence=0)
        self.assertTrue(any(item["channel"] == "activity" for item in first["items"]))
        answer = [item for item in first["items"] if item["channel"] == "answer"]
        self.assertEqual([item["text"] for item in answer], ["España, pingüino, acción, 😀"])
        second = browser.live_for_current_user(
            turn_uuid,
            after_sequence=first["last_sequence"],
        )
        self.assertEqual(second["items"], [])

    def test_answer_delta_requires_running_turn(self):
        turn_id, _, _ = self._committed_turn()
        with Registry(self.env.cr.dbname).cursor() as cr:
            env = api.Environment(cr, SUPERUSER_ID, {}, su=True)
            env["odoo.ai.turn"].browse(turn_id).write({"state": "cancelled"})
            cr.commit()
        with self.assertRaises(ValidationError):
            self.env["odoo.ai.turn.live.event"].append_answer_delta_independent(
                turn_id=turn_id,
                text="late",
            )

    def test_non_superuser_cannot_write_live_rows(self):
        turn_id, _, user_id = self._committed_turn()
        live = self.env["odoo.ai.turn.live.event"].with_user(user_id)
        if user_id == SUPERUSER_ID:
            other = self.env["res.users"].create(
                {
                    "name": "Phase 4 Limited Writer",
                    "login": f"p4-{uuid4()}@example.invalid",
                }
            )
            live = self.env["odoo.ai.turn.live.event"].with_user(other.id)
        with self.assertRaises(AccessError):
            live.append_answer_delta_independent(turn_id=turn_id, text="forbidden")
