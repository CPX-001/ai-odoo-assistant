from uuid import uuid4

from odoo import SUPERUSER_ID, api
from odoo.exceptions import AccessError, ValidationError
from odoo.modules.registry import Registry
from odoo.tests.common import TransactionCase


class TestReasoningSummaryProjection(TransactionCase):
    def setUp(self):
        self._committed_turn_refs = []
        self.addCleanup(self._cleanup_committed_turns)
        super().setUp()

    def _cleanup_committed_turns(self):
        if not self._committed_turn_refs:
            return
        turn_ids = [item[0] for item in self._committed_turn_refs]
        turn_uuids = [item[1] for item in self._committed_turn_refs]
        with Registry(self.env.cr.dbname).cursor() as cr:
            env = api.Environment(cr, SUPERUSER_ID, {}, su=True)
            env["odoo.ai.turn.live.event"].search(
                [("turn_uuid", "in", turn_uuids)]
            ).unlink()
            env["odoo.ai.turn"].browse(turn_ids).exists().unlink()
            cr.commit()

    def _committed_turn(self):
        with Registry(self.env.cr.dbname).cursor() as cr:
            env = api.Environment(cr, SUPERUSER_ID, {}, su=True)
            user = env.ref("base.user_admin")
            turn = env["odoo.ai.turn"].create(
                {
                    "turn_uuid": str(uuid4()),
                    "user_id": user.id,
                    "company_id": user.company_id.id,
                    "state": "running",
                    "input_message": "Readable reasoning summary projection",
                    "allowed_company_ids": [user.company_id.id],
                    "attempt_count": 1,
                    "max_attempts": 1,
                }
            )
            result = turn.id, turn.turn_uuid, user.id
            self._committed_turn_refs.append((turn.id, turn.turn_uuid))
            cr.commit()
            return result

    def test_readable_summary_has_separate_closed_live_channel(self):
        turn_id, turn_uuid, user_id = self._committed_turn()
        turn = self.env["odoo.ai.turn"].with_user(SUPERUSER_ID).browse(turn_id)

        self.env["odoo.ai.turn.event"].with_user(SUPERUSER_ID).append_for_turn(
            turn=turn,
            event_type="reasoning.summary.delta",
            title="Readable reasoning summary",
            payload={
                "item_id": "reasoning-1",
                "summary_index": 0,
                "text": "Comprobaré primero los contactos visibles.",
            },
        )

        live = self.env["odoo.ai.turn"].with_user(user_id).live_for_current_user(
            turn_uuid,
            after_sequence=0,
        )
        reasoning = [item for item in live["items"] if item["channel"] == "reasoning"]
        self.assertEqual(len(reasoning), 1)
        self.assertEqual(reasoning[0]["turn_id"], turn_uuid)
        self.assertEqual(reasoning[0]["item_id"], "reasoning-1")
        self.assertEqual(reasoning[0]["summary_index"], 0)
        self.assertEqual(
            reasoning[0]["text"],
            "Comprobaré primero los contactos visibles.",
        )
        encoded = repr(reasoning[0]).lower()
        for forbidden in ("raw_reasoning", "prompt", "arguments_json", "payload"):
            self.assertNotIn(forbidden, encoded)

    def test_raw_or_extra_reasoning_content_fails_closed(self):
        turn_id, _, _ = self._committed_turn()
        turn = self.env["odoo.ai.turn"].with_user(SUPERUSER_ID).browse(turn_id)

        with self.assertRaises(ValidationError):
            self.env["odoo.ai.turn.event"].with_user(SUPERUSER_ID).append_for_turn(
                turn=turn,
                event_type="reasoning.summary.delta",
                title="Readable reasoning summary",
                payload={
                    "item_id": "reasoning-1",
                    "summary_index": 0,
                    "text": "Safe summary",
                    "raw_reasoning": "must never cross",
                },
            )

        with self.assertRaises(ValidationError):
            self.env["odoo.ai.turn.live.event"].with_user(SUPERUSER_ID).append_reasoning_summary_independent(
                turn_id=turn_id,
                item_id="reasoning-1",
                summary_index=0,
                text="x" * 2049,
            )

    def test_live_reasoning_writer_is_host_internal_only(self):
        turn_id, _, user_id = self._committed_turn()
        if user_id == SUPERUSER_ID:
            self.skipTest("admin user is superuser in this database")
        with self.assertRaises(AccessError):
            self.env["odoo.ai.turn.live.event"].with_user(user_id).append_reasoning_summary_independent(
                turn_id=turn_id,
                item_id="reasoning-1",
                summary_index=0,
                text="No autorizado",
            )
