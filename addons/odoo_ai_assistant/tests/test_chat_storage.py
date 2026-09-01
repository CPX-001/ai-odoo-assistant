import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from odoo import Command
from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase
from odoo.tools import config

from ..runtime import RuntimePathError, RuntimePaths, detect_codex


class TestAssistantNativeStorage(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        internal_group = cls.env.ref("base.group_user")
        company = cls.env.company
        cls.user_a = cls.env["res.users"].create(
            {
                "name": "AI Conversation User A",
                "login": "ai-conversation-user-a",
                "company_id": company.id,
                "company_ids": [Command.set([company.id])],
                "groups_id": [Command.set([internal_group.id])],
            }
        )
        cls.user_b = cls.env["res.users"].create(
            {
                "name": "AI Conversation User B",
                "login": "ai-conversation-user-b",
                "company_id": company.id,
                "company_ids": [Command.set([company.id])],
                "groups_id": [Command.set([internal_group.id])],
            }
        )

    def test_exchange_and_history_are_owned_by_effective_user(self):
        env_a = self.env(user=self.user_a, su=False)
        store_a = env_a["odoo.ai.conversation"]
        conversation_id = store_a.append_exchange(
            conversation_uuid=None,
            user_message="Resume este pedido",
            assistant_message="Este es el resumen.",
        )

        history = store_a.history_payload(conversation_uuid=conversation_id)
        self.assertEqual(history["active_conversation_id"], conversation_id)
        self.assertIsNone(history["active_turn"])
        self.assertEqual([item["role"] for item in history["messages"]], ["user", "assistant"])
        self.assertIn("User: Resume este pedido", store_a.recent_text(conversation_id))

        env_b = self.env(user=self.user_b, su=False)
        self.assertFalse(
            env_b["odoo.ai.conversation"].search(
                [("conversation_uuid", "=", conversation_id)]
            )
        )
        with self.assertRaises(AccessError):
            env_b["odoo.ai.conversation"].delete_owned([conversation_id])

    def test_delete_owned_cascades_messages(self):
        env_a = self.env(user=self.user_a, su=False)
        store = env_a["odoo.ai.conversation"]
        conversation_id = store.append_exchange(
            conversation_uuid=None,
            user_message="Borra después este chat",
            assistant_message="De acuerdo.",
        )
        conversation = store._owned_conversation(conversation_id)
        message_ids = conversation.message_ids.ids
        self.assertEqual(store.delete_owned([conversation_id]), 1)
        self.assertFalse(store.search([("conversation_uuid", "=", conversation_id)]))
        self.assertFalse(env_a["odoo.ai.message"].search([("id", "in", message_ids)]))

    def test_completed_answer_history_keeps_its_public_activity_and_readable_summary(self):
        env_a = self.env(user=self.user_a, su=False)
        store = env_a["odoo.ai.conversation"]
        conversation_id = store.append_exchange(
            conversation_uuid=None,
            user_message="Crea datos relacionados",
            assistant_message="Datos creados y verificados.",
        )
        conversation = store._owned_conversation(conversation_id)
        assistant_message = conversation.message_ids.filtered(
            lambda message: message.role == "assistant"
        )
        turn = self.env["odoo.ai.turn"].create(
            {
                "conversation_id": conversation.id,
                "user_id": self.user_a.id,
                "company_id": self.user_a.company_id.id,
                "state": "completed",
                "input_message": "Crea datos relacionados",
                "assistant_message_id": assistant_message.id,
            }
        )
        binding = {
            "turn_ref_id": turn.id,
            "turn_uuid": turn.turn_uuid,
            "user_id": self.user_a.id,
            "company_id": self.user_a.company_id.id,
        }
        live = self.env["odoo.ai.turn.live.event"]
        live.create(
            {
                **binding,
                "sequence": 1,
                "channel": "activity",
                "kind": "capability.completed",
                "phase": "capability",
                "status": "completed",
                "label": "Registros creados",
                "capability": "odoo.workflow.batch_create_graph",
            }
        )
        live.create(
            {
                **binding,
                "sequence": 2,
                "channel": "reasoning",
                "reasoning_summary_delta": "Resumen legible",
                "reasoning_item_id": "reasoning-item-1",
                "reasoning_summary_index": 0,
            }
        )

        history = store.history_payload(conversation_uuid=conversation_id)
        activity = history["messages"][1]["activity"]

        self.assertIsNone(history["active_turn"])
        self.assertEqual(activity["turn_id"], turn.turn_uuid)
        self.assertEqual(activity["events"][0]["kind"], "capability.completed")
        self.assertEqual(
            activity["reasoning_summary_parts"],
            [{"key": "reasoning-item-1:0", "text": "Resumen legible"}],
        )

        queued = self.env["odoo.ai.turn"].create(
            {
                "conversation_id": conversation.id,
                "user_id": self.user_a.id,
                "company_id": self.user_a.company_id.id,
                "state": "queued",
                "input_message": "Continua con la operación",
            }
        )
        history = store.history_payload(conversation_uuid=conversation_id)
        self.assertEqual(
            history["active_turn"],
            {"turn_id": queued.turn_uuid, "state": "queued"},
        )


class TestAssistantRuntimeLayout(TransactionCase):
    def test_runtime_root_is_below_odoo_data_dir(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CODEX_HOME", None)
            paths = RuntimePaths.from_odoo()
        expected_parent = Path(config["data_dir"]).expanduser().resolve(strict=False)
        self.assertEqual(paths.root.parent, expected_parent)
        self.assertEqual(paths.codex_home.parent, paths.root)

    def test_runtime_reuses_absolute_host_codex_home_without_database_state(self):
        with TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"CODEX_HOME": directory}):
                paths = RuntimePaths.from_odoo().ensure()

            self.assertEqual(paths.codex_home, Path(directory).resolve())
            self.assertNotEqual(paths.codex_home.parent, paths.root)

    def test_runtime_rejects_relative_host_codex_home(self):
        with patch.dict(os.environ, {"CODEX_HOME": "relative-codex-home"}):
            with self.assertRaises(RuntimePathError):
                RuntimePaths.from_odoo()

    def test_codex_detection_requires_an_executable_file(self):
        with TemporaryDirectory() as directory:
            binary = Path(directory) / "codex"
            binary.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            self.assertEqual(detect_codex(str(binary)).state, "not_executable")
            binary.chmod(0o700)
            status = detect_codex(str(binary))
            self.assertTrue(status.ready)
            self.assertEqual(status.executable, binary.resolve())
