from datetime import UTC, datetime

from odoo import SUPERUSER_ID, Command
from odoo.tests.common import TransactionCase

from ..models.turn_control import TurnControlError


class TestAssistantTurnInterventions(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = cls.env["res.users"].create(
            {
                "name": "AI Turn Intervention User",
                "login": "ai-turn-intervention-user",
                "company_id": cls.env.company.id,
                "company_ids": [Command.set([cls.env.company.id])],
                "groups_id": [Command.set([cls.env.ref("base.group_user").id])],
            }
        )

    def _env(self):
        return self.env(user=self.user, su=False)

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

    def _queued_turn(self, suffix):
        return self._env()["odoo.ai.turn"].enqueue_for_current_user(
            message="Analiza los contactos",
            screen=self._screen(),
            client_request_id=f"turn.intervention.{suffix}",
        )

    def _rows(self, turn_id):
        turn = self._env()["odoo.ai.turn"]._owned_turn(turn_id)
        return self.env["odoo.ai.turn.intervention"].with_user(SUPERUSER_ID).search(
            [("turn_ref_id", "=", turn.id)], order="sequence"
        )

    def test_queued_interventions_keep_same_turn_and_monotonic_order(self):
        queued = self._queued_turn("queued.0001")
        env = self._env()

        first = env["odoo.ai.turn"].redirect_for_current_user(
            queued["turn_id"],
            "Primero céntrate en clientes",
            "ui:intervention-queued-0001",
        )
        second = env["odoo.ai.turn"].redirect_for_current_user(
            queued["turn_id"],
            "Después limita el periodo a agosto",
            "ui:intervention-queued-0002",
        )

        rows = self._rows(queued["turn_id"])
        self.assertEqual(first["turn_id"], queued["turn_id"])
        self.assertEqual(second["turn_id"], queued["turn_id"])
        self.assertEqual(first["state"], "queued")
        self.assertEqual(second["state"], "queued")
        self.assertEqual(rows.mapped("sequence"), [1, 2])
        self.assertEqual(rows.mapped("state"), ["pending", "pending"])

    def test_running_intervention_is_durable_before_provider_consumption(self):
        queued = self._queued_turn("running.0001")
        env = self._env()
        turn = env["odoo.ai.turn"]._owned_turn(queued["turn_id"])
        turn.with_user(SUPERUSER_ID).write(
            {"state": "running", "lease_token": "turn-intervention-running-lease"}
        )

        redirected = env["odoo.ai.turn"].redirect_for_current_user(
            queued["turn_id"],
            "Corrige: usa sólo contactos activos",
            "ui:intervention-running-0001",
        )

        turn.invalidate_recordset(["state"])
        rows = self._rows(queued["turn_id"])
        control = self.env["odoo.ai.turn.control"].with_user(SUPERUSER_ID).search(
            [("turn_ref_id", "=", turn.id)], limit=1
        )
        self.assertEqual(redirected["turn_id"], queued["turn_id"])
        self.assertEqual(redirected["state"], "running")
        self.assertEqual(turn.state, "running")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows.sequence, 1)
        self.assertEqual(rows.state, "pending")
        self.assertEqual(control.intervention_sequence, 1)
        self.assertEqual(control.applied_sequence, 0)

    def test_intervention_count_budget_rejects_the_seventeenth(self):
        queued = self._queued_turn("budget.0001")
        env = self._env()
        for index in range(16):
            result = env["odoo.ai.turn"].redirect_for_current_user(
                queued["turn_id"],
                f"Corrección ordenada {index + 1}",
                f"ui:intervention-budget-{index + 1:04d}",
            )
            self.assertEqual(result["sequence"], index + 1)

        with self.assertRaises(TurnControlError) as captured:
            env["odoo.ai.turn"].redirect_for_current_user(
                queued["turn_id"],
                "Esta corrección debe exceder el límite",
                "ui:intervention-budget-0017",
            )
        self.assertEqual(captured.exception.code, "turn_redirect_limit_exceeded")
        self.assertEqual(len(self._rows(queued["turn_id"])), 16)
