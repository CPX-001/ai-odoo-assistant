from __future__ import annotations

import base64
from datetime import UTC, datetime

from odoo import Command
from odoo.addons.odoo_ai_assistant.runtime.capabilities.contracts import CapabilityContext
from odoo.addons.odoo_ai_assistant.runtime.capabilities.providers.assistant_knowledge import (
    _preview,
    _verify,
    ingest_attachment,
)
from odoo.addons.odoo_ai_assistant.runtime.capabilities.registry import (
    discover_capabilities_for_env,
)
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestPhase9KnowledgeCapability(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        internal_group = cls.env.ref("base.group_user")
        cls.user = cls.env["res.users"].create(
            {
                "name": "P9 Knowledge Capability User",
                "login": "p9-knowledge-capability-user",
                "company_id": cls.env.company.id,
                "company_ids": [Command.set([cls.env.company.id])],
                "groups_id": [Command.set([internal_group.id])],
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
            "model": None,
            "res_id": None,
            "selected_ids": [],
            "view_type": "list",
        }

    def test_ingest_current_turn_attachment_is_previewable_verified_and_idempotent(self):
        env = self._env()
        attachment = env["odoo.ai.knowledge.attachment"].create_upload(
            filename="capability-source.txt",
            mimetype="text/plain",
            data=base64.b64encode(b"P9_CAPABILITY_INGEST_MARKER"),
        )
        result = env["odoo.ai.turn"].enqueue_for_current_user(
            message=(
                "Add this file to company Knowledge."
                f"\n[[odoo_ai_attachment:{attachment.token}]]"
            ),
            screen=self._screen(),
            client_request_id="request.p9.knowledge.capability.0001",
        )
        context = CapabilityContext(env=env, turn_id=result["turn_id"])
        arguments = {"attachment_id": attachment.id, "access_mode": "company"}

        preview = _preview(context, arguments)
        self.assertEqual(preview.summary["operation"], "knowledge_ingest_attachment")
        self.assertEqual(preview.summary["attachment_id"], attachment.id)
        self.assertEqual(
            preview.precondition_fingerprint,
            f"sha256:{attachment.fingerprint}",
        )

        first = ingest_attachment(context, arguments)
        self.assertTrue(first["source_id"])
        self.assertEqual(first["access_mode"], "company")
        self.assertTrue(first["queued_for_indexing"])
        verification = _verify(context, arguments)
        self.assertTrue(verification.verified)
        self.assertEqual(verification.summary["source_id"], first["source_id"])

        second = ingest_attachment(context, arguments)
        self.assertEqual(second["source_id"], first["source_id"])
        self.assertEqual(
            env["odoo.ai.knowledge.source"].search_count(
                [("id", "=", first["source_id"])]
            ),
            1,
        )

        definition = discover_capabilities_for_env(env).resolve(
            "assistant.knowledge.ingest_attachment"
        )
        self.assertEqual(definition.max_calls, 8)
