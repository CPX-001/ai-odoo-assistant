from datetime import UTC, datetime, timedelta

from odoo import Command, SUPERUSER_ID, api, fields
from odoo.exceptions import AccessError
from odoo.modules.registry import Registry
from odoo.tests.common import TransactionCase

from ..models.turn_queue import _recover_stale_turns


class TestAssistantTurnQueue(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        internal_group = cls.env.ref("base.group_user")
        company = cls.env.company
        cls.user_a = cls.env["res.users"].create(
            {
                "name": "AI Queue User A",
                "login": "ai-queue-user-a",
                "company_id": company.id,
                "company_ids": [Command.set([company.id])],
                "groups_id": [Command.set([internal_group.id])],
            }
        )
        cls.user_b = cls.env["res.users"].create(
            {
                "name": "AI Queue User B",
                "login": "ai-queue-user-b",
                "company_id": company.id,
                "company_ids": [Command.set([company.id])],
                "groups_id": [Command.set([internal_group.id])],
            }
        )

    def _screen(self):
        return {
            "action_id": None,
            "allowed_context_subset": {},
            "captured_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "menu_id": None,
            "model": "res.partner",
            "res_id": None,
            "selected_ids": [],
            "view_type": "list",
        }

    def test_enqueue_persists_user_turn_and_initial_event(self):
        env = self.env(user=self.user_a, su=False)
        result = env["odoo.ai.turn"].enqueue_for_current_user(
            message="Lista los contactos visibles",
            screen=self._screen(),
            client_request_id="request.queue.0001",
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["state"], "queued")
        self.assertEqual([item["type"] for item in result["events"]], ["queued"])
        turn = env["odoo.ai.turn"].search([("turn_uuid", "=", result["turn_id"])], limit=1)
        self.assertEqual(turn.user_id, self.user_a)
        self.assertFalse(turn.env.su)
        self.assertEqual(turn.user_message_id.content, "Lista los contactos visibles")
        self.assertFalse(turn.assistant_message_id)
        self.assertEqual(turn.allowed_company_ids, [env.company.id])

    def test_enqueue_is_idempotent_for_client_request_id(self):
        env = self.env(user=self.user_a, su=False)
        first = env["odoo.ai.turn"].enqueue_for_current_user(
            message="Cuenta contactos",
            screen=self._screen(),
            client_request_id="request.queue.0002",
        )
        second = env["odoo.ai.turn"].enqueue_for_current_user(
            message="Este segundo payload no debe crear otro turno",
            screen=self._screen(),
            client_request_id="request.queue.0002",
        )
        self.assertEqual(first["turn_id"], second["turn_id"])
        self.assertEqual(
            env["odoo.ai.turn"].search_count(
                [("user_id", "=", self.user_a.id), ("client_request_id", "=", "request.queue.0002")]
            ),
            1,
        )

    def test_turn_status_is_private_to_originating_user(self):
        env_a = self.env(user=self.user_a, su=False)
        result = env_a["odoo.ai.turn"].enqueue_for_current_user(
            message="Consulta segura",
            screen=self._screen(),
            client_request_id="request.queue.0003",
        )
        env_b = self.env(user=self.user_b, su=False)
        with self.assertRaises(AccessError):
            env_b["odoo.ai.turn"]._owned_turn(result["turn_id"])

    def test_cancel_queued_turn_is_terminal_and_append_only(self):
        env = self.env(user=self.user_a, su=False)
        result = env["odoo.ai.turn"].enqueue_for_current_user(
            message="Cancela antes de ejecutar",
            screen=self._screen(),
            client_request_id="request.queue.0004",
        )
        cancelled = env["odoo.ai.turn"].cancel_for_current_user(result["turn_id"])
        self.assertEqual(cancelled["state"], "cancelled")
        self.assertEqual([item["type"] for item in cancelled["events"]], ["queued", "cancelled"])

    def test_event_payload_drops_sensitive_keys(self):
        env = self.env(user=self.user_a, su=False)
        result = env["odoo.ai.turn"].enqueue_for_current_user(
            message="Evento seguro",
            screen=self._screen(),
            client_request_id="request.queue.0005",
        )
        turn = env["odoo.ai.turn"]._owned_turn(result["turn_id"])
        technical_event = self.env["odoo.ai.turn.event"].with_user(SUPERUSER_ID)
        technical_event.append_for_turn(
            turn=turn.with_user(SUPERUSER_ID),
            event_type="retrieval",
            title="Consultando datos",
            payload={"count": 2, "secret_token": "must-not-leak", "detail": "bounded"},
        )
        status = env["odoo.ai.turn"].status_for_current_user(result["turn_id"], after_sequence=1)
        self.assertEqual(len(status["events"]), 1)
        self.assertEqual(status["events"][0]["payload"], {"count": 2, "detail": "bounded"})

    def test_stale_worker_after_write_barrier_requires_recovery_without_retry(self):
        """A persisted barrier is a one-way retry boundary even with attempts remaining."""

        dbname = self.env.cr.dbname
        turn_id = None
        try:
            with Registry(dbname).cursor() as cr:
                env = api.Environment(cr, SUPERUSER_ID, {}, su=True)
                admin = env.ref("base.user_admin")
                company = admin.company_id
                turn = env["odoo.ai.turn"].create(
                    {
                        "turn_uuid": "00000000-0000-4000-8000-000000000901",
                        "user_id": admin.id,
                        "company_id": company.id,
                        "state": "running",
                        "queued_at": fields.Datetime.now() - timedelta(minutes=10),
                        "started_at": fields.Datetime.now() - timedelta(minutes=9),
                        "heartbeat_at": fields.Datetime.now() - timedelta(minutes=6),
                        "lease_expires_at": fields.Datetime.now() - timedelta(seconds=1),
                        "lease_token": "stale-after-write-barrier",
                        "attempt_count": 1,
                        "max_attempts": 3,
                        "write_barrier": True,
                        "allowed_company_ids": [company.id],
                    }
                )
                turn_id = turn.id
                cr.commit()

            _recover_stale_turns(dbname)

            with Registry(dbname).cursor() as cr:
                env = api.Environment(cr, SUPERUSER_ID, {}, su=True)
                turn = env["odoo.ai.turn"].browse(turn_id).exists()
                self.assertTrue(turn)
                self.assertEqual(turn.state, "recovery_required")
                self.assertEqual(turn.error_code, "worker_lost_after_write_barrier")
                self.assertEqual(turn.attempt_count, 1)
                self.assertEqual(turn.max_attempts, 3)
                self.assertFalse(turn.lease_token)
                self.assertFalse(turn.lease_expires_at)
                event_types = env["odoo.ai.turn.event"].search(
                    [("turn_id", "=", turn.id)], order="sequence"
                ).mapped("event_type")
                self.assertIn("recovery_required", event_types)
                self.assertNotIn("requeued", event_types)
        finally:
            if turn_id is not None:
                with Registry(dbname).cursor() as cr:
                    env = api.Environment(cr, SUPERUSER_ID, {}, su=True)
                    turn = env["odoo.ai.turn"].browse(turn_id).exists()
                    if turn:
                        turn.unlink()
                    cr.commit()
