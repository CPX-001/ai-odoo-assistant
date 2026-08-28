"""Deterministic Odoo coverage for production Phase 3 public activity wiring."""
from uuid import uuid4

from odoo import SUPERUSER_ID, api
from odoo.exceptions import AccessError, ValidationError
from odoo.modules.registry import Registry
from odoo.tests.common import TransactionCase


class TestPhase3PublicActivityProjection(TransactionCase):
    def setUp(self):
        self._committed_turn_refs = []
        # Register before TransactionCase adds its savepoint rollback cleanups so
        # these externally committed fixtures are removed after that rollback.
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
                    "input_message": "Phase 3 public projection",
                    "allowed_company_ids": [user.company_id.id],
                    "attempt_count": 1,
                    "max_attempts": 1,
                }
            )
            result = turn.id, turn.turn_uuid, user.id
            self._committed_turn_refs.append((turn.id, turn.turn_uuid))
            cr.commit()
            return result

    def test_internal_capability_event_projects_closed_public_resource(self):
        turn_id, turn_uuid, user_id = self._committed_turn()
        turn = self.env["odoo.ai.turn"].with_user(SUPERUSER_ID).browse(turn_id)
        self.env["odoo.ai.turn.event"].with_user(SUPERUSER_ID).append_for_turn(
            turn=turn,
            event_type="tool.started",
            title="Query Odoo records",
            payload={
                "capability": "odoo.query_records",
                "model": "res.partner",
                "record_id": 7,
                "arguments_json": "must-not-project",
                "prompt": "must-not-project",
            },
        )
        public = self.env["odoo.ai.turn"].with_user(user_id).public_events_for_current_user(
            turn_uuid,
            after_sequence=0,
        )
        self.assertEqual(len(public["events"]), 1)
        event = public["events"][0]
        self.assertEqual(event["kind"], "capability.started")
        self.assertEqual(event["capability"], "odoo.query_records")
        self.assertEqual(event["resource"]["model"], "res.partner")
        self.assertEqual(event["resource"]["record_ids"], [7])
        encoded = repr(event).lower()
        for forbidden in ("arguments_json", "must-not-project", "prompt", "payload"):
            self.assertNotIn(forbidden, encoded)

    def test_second_cursor_observes_public_event_before_worker_commit(self):
        turn_id, turn_uuid, user_id = self._committed_turn()
        dbname = self.env.cr.dbname
        with Registry(dbname).cursor() as worker_cr:
            worker = api.Environment(worker_cr, SUPERUSER_ID, {}, su=True)
            turn = worker["odoo.ai.turn"].browse(turn_id)
            worker["odoo.ai.turn.event"].append_for_turn(
                turn=turn,
                event_type="tool.started",
                title="Query Odoo records",
                payload={"capability": "odoo.query_records", "model": "res.partner"},
            )
            # Deliberately do not commit worker_cr. The public event must have committed through
            # its independent live cursor rather than relying on browser timers or worker commit.
            with Registry(dbname).cursor() as observer_cr:
                observer = api.Environment(observer_cr, user_id, {}, su=False)
                public = observer["odoo.ai.turn"].public_events_for_current_user(
                    turn_uuid,
                    after_sequence=0,
                )
                self.assertTrue(
                    any(event["kind"] == "capability.started" for event in public["events"])
                )

    def test_private_or_malformed_public_event_fails_closed(self):
        turn_id, _, user_id = self._committed_turn()
        with self.assertRaises(ValidationError):
            self.env["odoo.ai.turn.event"].with_user(SUPERUSER_ID).append_public_independent(
                turn_id=turn_id,
                kind="agent.thinking",
                phase="provider",
                status="running",
                label="private",
                resource=None,
                capability=None,
                progress=None,
                diagnostic_code=None,
            )
        if user_id != SUPERUSER_ID:
            with self.assertRaises(AccessError):
                self.env["odoo.ai.turn.live.event"].with_user(user_id).append_activity_independent(
                    turn_id=turn_id,
                    kind="provider.connected",
                    phase="provider",
                    status="completed",
                    label="Provider connected",
                )
