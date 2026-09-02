from __future__ import annotations

import base64
from datetime import UTC, datetime

from odoo import Command
from odoo.addons.odoo_ai_assistant.runtime.capabilities.contracts import (
    CapabilityContext,
)
from odoo.addons.odoo_ai_assistant.runtime.capabilities.evidence import (
    EvidenceFreshness,
    EvidenceKind,
    EvidenceProviderCatalog,
    EvidenceSearchRequest,
    EvidenceTrust,
)
from odoo.addons.odoo_ai_assistant.runtime.capabilities.knowledge_evidence import (
    build_company_knowledge_evidence_provider,
)
from odoo.addons.odoo_ai_assistant.runtime.capabilities.registry import (
    discover_capabilities_for_env,
)
from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestPhase9Knowledge(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        company = cls.env.company
        internal_group = cls.env.ref("base.group_user")
        cls.user_a = cls.env["res.users"].create(
            {
                "name": "P9 Knowledge User A",
                "login": "p9-knowledge-user-a",
                "company_id": company.id,
                "company_ids": [Command.set([company.id])],
                "groups_id": [Command.set([internal_group.id])],
            }
        )
        cls.user_b = cls.env["res.users"].create(
            {
                "name": "P9 Knowledge User B",
                "login": "p9-knowledge-user-b",
                "company_id": company.id,
                "company_ids": [Command.set([company.id])],
                "groups_id": [Command.set([internal_group.id])],
            }
        )

    def _env(self, user):
        return self.env(user=user, su=False)

    def _binary(self, text: str) -> bytes:
        return base64.b64encode(text.encode("utf-8"))

    def _source(self, env, *, name: str, text: str, access_mode="company"):
        source = env["odoo.ai.knowledge.source"].create(
            {
                "name": name,
                "filename": f"{name}.txt",
                "mimetype": "text/plain",
                "data": self._binary(text),
                "access_mode": access_mode,
            }
        )
        source.action_process_now()
        return source

    def _context(self, env, *, turn_id="p9-knowledge-test"):
        return CapabilityContext(env=env, turn_id=turn_id)

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

    def test_source_lifecycle_fts_citation_and_reindex_staleness(self):
        env = self._env(self.user_a)
        source = env["odoo.ai.knowledge.source"].create(
            {
                "name": "Support handbook",
                "filename": "support-handbook.txt",
                "mimetype": "text/plain",
                "data": self._binary(
                    "P9 exact marker alpha-7391.\n\nEscalate critical tickets to the duty manager."
                ),
                "access_mode": "company",
            }
        )
        self.assertEqual(source.state, "uploaded")
        self.assertEqual(source.version, 0)

        source.action_process_now()
        self.assertEqual(source.state, "active")
        self.assertEqual(source.version, 1)
        self.assertGreater(source.chunk_count, 0)
        self.assertEqual(source.content_fingerprint, source.indexed_fingerprint)

        catalog = EvidenceProviderCatalog((build_company_knowledge_evidence_provider(),))
        context = self._context(env)
        batch = catalog.search(
            context,
            EvidenceSearchRequest(
                query="alpha-7391 duty manager",
                kinds=(EvidenceKind.DOCUMENT,),
            ),
        )
        self.assertTrue(batch.refs)
        ref = batch.refs[0]
        item = catalog.fetch(context, ref)
        self.assertIn("alpha-7391", item.excerpt)
        self.assertEqual(ref.trust, EvidenceTrust.USER_CONTENT)
        self.assertEqual(ref.citation["source_uuid"], source.source_uuid)
        self.assertEqual(ref.citation["version"], 1)
        self.assertEqual(
            item.to_untrusted_projection()["trust_boundary"],
            "untrusted_data",
        )
        natural_results = env["odoo.ai.knowledge.source"].lexical_search(
            "According to the handbook, who should receive critical tickets? "
            "Include the exact marker."
        )
        self.assertTrue(
            any(chunk.source_id == source for chunk, _score in natural_results)
        )

        source.write(
            {
                "data": self._binary(
                    "P9 exact marker beta-8842.\n\nEscalate critical tickets to the incident lead."
                )
            }
        )
        self.assertEqual(source.state, "uploaded")
        stale_before_reindex = catalog.fetch(context, ref)
        self.assertEqual(stale_before_reindex.ref.freshness, EvidenceFreshness.STALE)

        source.action_process_now()
        self.assertEqual(source.version, 2)
        stale_after_reindex = catalog.fetch(context, ref)
        self.assertEqual(stale_after_reindex.ref.freshness, EvidenceFreshness.STALE)
        new_batch = catalog.search(
            context,
            EvidenceSearchRequest(
                query="beta-8842 incident lead",
                kinds=(EvidenceKind.DOCUMENT,),
            ),
        )
        self.assertTrue(new_batch.refs)
        self.assertEqual(new_batch.refs[0].citation["version"], 2)

    def test_company_private_acl_and_host_owned_index(self):
        env_a = self._env(self.user_a)
        env_b = self._env(self.user_b)
        company_source = self._source(
            env_a,
            name="company-policy-p9",
            text="company-visible-marker-p9",
            access_mode="company",
        )
        private_source = self._source(
            env_a,
            name="private-notes-p9",
            text="private-only-marker-p9",
            access_mode="private",
        )

        visible_to_b = env_b["odoo.ai.knowledge.source"].search([])
        self.assertIn(company_source.id, visible_to_b.ids)
        self.assertNotIn(private_source.id, visible_to_b.ids)
        self.assertTrue(
            env_b["odoo.ai.knowledge.source"].lexical_search(
                "company-visible-marker-p9"
            )
        )
        self.assertFalse(
            env_b["odoo.ai.knowledge.source"].lexical_search(
                "private-only-marker-p9"
            )
        )

        with self.assertRaises(AccessError):
            company_source.with_env(env_a).write({"owner_user_id": self.user_b.id})
        with self.assertRaises(AccessError):
            env_a["odoo.ai.knowledge.chunk"].create(
                {
                    "source_id": company_source.id,
                    "sequence": 999,
                    "source_version": company_source.version,
                    "content": "poisoned direct chunk",
                    "char_start": 0,
                    "char_end": 21,
                    "content_fingerprint": "0" * 64,
                }
            )

    def test_chat_attachment_binding_is_clean_and_retry_safe(self):
        env = self._env(self.user_a)
        attachment = env["odoo.ai.knowledge.attachment"].create_upload(
            filename="chat-source.txt",
            mimetype="text/plain",
            data=self._binary("chat-ingest-marker-p9"),
        )
        message = (
            "Añade este archivo a Knowledge."
            f"\n[[odoo_ai_attachment:{attachment.token}]]"
        )
        result = env["odoo.ai.turn"].enqueue_for_current_user(
            message=message,
            screen=self._screen(),
            client_request_id="request.p9.knowledge.attachment.0001",
        )
        self.assertTrue(result["ok"])
        turn = env["odoo.ai.turn"]._owned_turn(result["turn_id"])
        self.assertEqual(turn.user_message_id.content, "Añade este archivo a Knowledge.")
        self.assertNotIn("odoo_ai_attachment", turn.user_message_id.content)
        self.assertIn("Host attachment references", turn.input_message)
        self.assertIn(f'"attachment_id":{attachment.id}', turn.input_message)
        self.assertEqual(attachment.turn_id.id, turn.id)

        retry = env["odoo.ai.turn"].enqueue_for_current_user(
            message=message,
            screen=self._screen(),
            client_request_id="request.p9.knowledge.attachment.0001",
        )
        self.assertEqual(retry["turn_id"], turn.turn_uuid)

        count_before = env["odoo.ai.turn"].search_count([])
        with self.assertRaises(AccessError):
            env["odoo.ai.turn"].enqueue_for_current_user(
                message=message,
                screen=self._screen(),
                client_request_id="request.p9.knowledge.attachment.0002",
            )
        self.assertEqual(env["odoo.ai.turn"].search_count([]), count_before)

    def test_knowledge_ingestion_capability_is_discovered(self):
        env = self._env(self.user_a)
        registry = discover_capabilities_for_env(env)
        names = {definition.name for definition in registry.definitions}
        self.assertIn("assistant.knowledge.ingest_attachment", names)
