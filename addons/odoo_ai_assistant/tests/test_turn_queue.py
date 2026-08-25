from datetime import UTC, datetime

from odoo import Command, SUPERUSER_ID
from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase


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
