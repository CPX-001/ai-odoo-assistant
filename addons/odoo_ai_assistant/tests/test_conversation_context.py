import json
from datetime import UTC, datetime

from odoo import SUPERUSER_ID, Command
from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase


class TestAssistantConversationContext(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        internal_group = cls.env.ref("base.group_user")
        company = cls.env.company
        cls.user = cls.env["res.users"].create(
            {
                "name": "AI Conversation Context User",
                "login": "ai-conversation-context-user",
                "company_id": company.id,
                "company_ids": [Command.set([company.id])],
                "groups_id": [Command.set([internal_group.id])],
            }
        )

    def _env(self):
        return self.env(user=self.user, su=False)

    def _screen(self, *, res_id=None):
        return {
            "action_id": None,
            "allowed_context_subset": {},
            "captured_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "menu_id": None,
            "model": "res.partner",
            "res_id": res_id,
            "selected_ids": [],
            "view_type": "form" if res_id else "list",
        }

    def _enqueue(self, message, *, conversation_uuid=None, request_id, res_id=None):
        env = self._env()
        result = env["odoo.ai.turn"].enqueue_for_current_user(
            message=message,
            screen=self._screen(res_id=res_id),
            conversation_uuid=conversation_uuid,
            client_request_id=request_id,
        )
        return env["odoo.ai.turn"]._owned_turn(result["turn_id"])

    def _complete(self, turn, answer, *, with_effect=False):
        technical = turn.with_user(SUPERUSER_ID)
        assistant = technical.env["odoo.ai.message"].create(
            {
                "conversation_id": technical.conversation_id.id,
                "role": "assistant",
                "content": answer,
                "internal_workflow": "AGENT",
            }
        )
        values = {
            "state": "completed",
            "assistant_message_id": assistant.id,
        }
        if with_effect:
            values["capability_plan_payload"] = {
                "format_version": 1,
                "answer": answer,
                "confidence": "high",
                "human_approved": True,
                "plan": {
                    "state": "completed",
                    "steps": [
                        {
                            "position": 1,
                            "capability": "odoo.record.patch",
                            "state": "completed",
                            "result": {
                                "operation": "update",
                                "model": "res.partner",
                                "record_ids": [41, 42],
                            },
                        }
                    ],
                },
            }
        technical.write(values)

    def test_context_uses_turn_causality_and_excludes_future_messages(self):
        turn_a = self._enqueue(
            "Primero recuerda ALFA-CAUSAL",
            request_id="request.context.a.0001",
            res_id=11,
        )
        conversation_uuid = turn_a.conversation_id.conversation_uuid
        turn_b = self._enqueue(
            "Segundo mensaje que aún no debe entrar",
            conversation_uuid=conversation_uuid,
            request_id="request.context.b.0001",
            res_id=22,
        )
        turn_c = self._enqueue(
            "Tercer mensaje futuro",
            conversation_uuid=conversation_uuid,
            request_id="request.context.c.0001",
            res_id=33,
        )

        # The previous Assistant reply is deliberately persisted after B and C user
        # messages. Context order must still follow causal turn order, not message ids.
        self._complete(
            turn_a,
            "Respuesta de A posterior a los mensajes B y C.",
            with_effect=True,
        )

        snapshot_b = turn_b.conversation_context_snapshot()

        self.assertEqual(snapshot_b["format_version"], 1)
        self.assertEqual(snapshot_b["conversation_id"], conversation_uuid)
        self.assertEqual(snapshot_b["revision"], 1)
        self.assertEqual(
            [item["role"] for item in snapshot_b["recent_messages"]],
            ["user", "assistant"],
        )
        recent_text = " ".join(
            item["content"] for item in snapshot_b["recent_messages"]
        )
        self.assertIn("ALFA-CAUSAL", recent_text)
        self.assertIn("Respuesta de A", recent_text)
        self.assertNotIn("Segundo mensaje", recent_text)
        self.assertNotIn("Tercer mensaje", recent_text)
        self.assertEqual(
            snapshot_b["rolling_summary"][-1]["turn_id"],
            turn_a.turn_uuid,
        )
        self.assertEqual(
            snapshot_b["verified_effect_refs"],
            [
                {
                    "turn_id": turn_a.turn_uuid,
                    "position": 1,
                    "capability": "odoo.record.patch",
                    "state": "completed",
                    "operation": "update",
                    "resource": {
                        "model": "res.partner",
                        "record_ids": [41, 42],
                    },
                }
            ],
        )
        self.assertIn(
            {"kind": "odoo_record", "model": "res.partner", "res_id": 22},
            snapshot_b["active_refs"],
        )

        provider_context = json.loads(
            self._env()["odoo.ai.embedded.runtime"]._conversation_summary(turn_b)
        )
        self.assertEqual(provider_context, snapshot_b)

        # C is intentionally still queued. Its existence cannot mutate B's frozen
        # checkpoint even after B later completes.
        frozen_b = turn_b.conversation_context_snapshot()
        self._complete(turn_b, "Respuesta final de B.")
        self.assertEqual(turn_b.conversation_context_snapshot(), frozen_b)

        snapshot_c = turn_c.conversation_context_snapshot()
        self.assertEqual(snapshot_c["revision"], 2)
        self.assertEqual(
            [item["turn_id"] for item in snapshot_c["rolling_summary"][-2:]],
            [turn_a.turn_uuid, turn_b.turn_uuid],
        )
        c_recent = " ".join(item["content"] for item in snapshot_c["recent_messages"])
        self.assertIn("Segundo mensaje", c_recent)
        self.assertIn("Respuesta final de B", c_recent)
        self.assertNotIn("Tercer mensaje futuro", c_recent)

    def test_nonterminal_predecessor_is_rejected_instead_of_leaking_future_state(self):
        turn_a = self._enqueue(
            "Predecesor aún pendiente",
            request_id="request.context.pending.a",
        )
        turn_b = self._enqueue(
            "Sucesor bloqueado",
            conversation_uuid=turn_a.conversation_id.conversation_uuid,
            request_id="request.context.pending.b",
        )

        with self.assertRaises(ValidationError):
            turn_b.conversation_context_snapshot()

        turn_a.with_user(SUPERUSER_ID).write(
            {
                "state": "failed",
                "error_code": "codex_turn_failed",
            }
        )
        snapshot = turn_b.conversation_context_snapshot()
        self.assertEqual(snapshot["rolling_summary"][-1]["state"], "failed")
        self.assertEqual(
            snapshot["rolling_summary"][-1]["failure_code"],
            "codex_turn_failed",
        )

    def test_context_checkpoint_is_host_managed_and_bounded(self):
        turn = self._enqueue(
            "Contexto protegido",
            request_id="request.context.protected",
        )

        with self.assertRaises(ValidationError):
            turn.write({"conversation_context_payload": {"format_version": 1}})
        with self.assertRaises(ValidationError):
            turn.with_user(SUPERUSER_ID).write(
                {"conversation_context_payload": {"format_version": 1}}
            )

        # A first turn has no predecessors but still gets a versioned bounded
        # checkpoint with the captured Odoo language fallback and current screen ref.
        snapshot = turn.conversation_context_snapshot()
        encoded = turn.conversation_context_for_provider()
        self.assertLessEqual(len(encoded), 8_000)
        self.assertEqual(json.loads(encoded), snapshot)
        self.assertEqual(
            snapshot["session_settings"].get("odoo_user_language"),
            turn.lang,
        )
        self.assertEqual(snapshot["rolling_summary"], [])
        self.assertEqual(snapshot["verified_effect_refs"], [])
