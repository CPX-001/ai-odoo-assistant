from __future__ import annotations

import base64
from datetime import UTC, datetime
from io import BytesIO

from odoo import Command
from odoo.addons.odoo_ai_assistant.runtime.capabilities.attachment_evidence import (
    build_turn_attachment_evidence_provider,
)
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
from odoo.addons.odoo_ai_assistant.runtime.capabilities.knowledge_routing import (
    document_overview_requested,
    document_overview_subject,
)
from odoo.addons.odoo_ai_assistant.runtime.capabilities.registry import (
    discover_capabilities_for_env,
)
from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase, tagged
from reportlab.pdfgen import canvas


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

    def _pdf_binary(self, text: str) -> bytes:
        buffer = BytesIO()
        document = canvas.Canvas(buffer)
        document.drawString(72, 760, text)
        document.save()
        return base64.b64encode(buffer.getvalue())

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

        catalog = EvidenceProviderCatalog(
            (build_company_knowledge_evidence_provider(),)
        )
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

    def test_pdf_type_is_detected_and_text_is_indexed(self):
        env = self._env(self.user_a)
        source = env["odoo.ai.knowledge.source"].create(
            {
                "name": "PDF architecture notes",
                "filename": "architecture-hardening.pdf",
                "mimetype": "pdf",
                "data": self._pdf_binary("Architecture hardening recovery boundary"),
                "access_mode": "company",
            }
        )

        self.assertEqual(source.mimetype, "application/pdf")
        source.action_process_now()
        self.assertEqual(source.state, "active")
        self.assertIn("Architecture hardening", source.chunk_ids[0].content)

    def test_knowledge_search_uses_content_and_filename_as_retrieval_signals(self):
        env = self._env(self.user_a)
        source = self._source(
            env,
            name="Architecture_Hardening_Packet",
            text="The recovery boundary rejects an unverified write barrier.",
        )
        dori_source = self._source(
            env,
            name="DoriDori_Inventario_IT",
            text="Inventario interno de equipos y sistemas.",
        )

        by_name = env["odoo.ai.knowledge.source"].lexical_search(
            "¿Tienes alguna referencia de architecture hardening?"
        )
        by_content = env["odoo.ai.knowledge.source"].lexical_search(
            "recovery boundary unverified write barrier"
        )
        by_noisy_name = env["odoo.ai.knowledge.source"].lexical_search(
            "tienes alguna info sore dori dori?"
        )

        self.assertTrue(any(chunk.source_id == source for chunk, _score in by_name))
        self.assertTrue(any(chunk.source_id == source for chunk, _score in by_content))
        self.assertTrue(
            any(chunk.source_id == dori_source for chunk, _score in by_noisy_name)
        )

    def test_broad_infrastructure_question_expands_one_whole_short_document(self):
        env = self._env(self.user_a)
        paragraphs = [
            "Dori Dori network systems overview marker. " + "gateway " * 430,
            "Hyper-V servers and virtual machines. " + "server " * 430,
            "Business applications, databases and access control. " + "application " * 330,
            "Backups, risks and pending maintenance. " + "recovery " * 400,
        ]
        source = self._source(
            env,
            name="Dori Dori infrastructure",
            text="\n\n".join(paragraphs),
        )
        self.assertGreater(source.chunk_count, 1)
        self.assertLessEqual(source.chunk_count, 8)
        question = (
            "¿Puedes decirme cómo está actualmente montada la red y los sistemas "
            "de Dori Dori?"
        )
        self.assertTrue(document_overview_requested(question))
        self.assertEqual(document_overview_subject(question), "dori")
        self.assertFalse(
            document_overview_requested("¿Qué puerto usa la arquitectura del gateway?")
        )

        catalog = EvidenceProviderCatalog(
            (build_company_knowledge_evidence_provider(),)
        )
        batch = catalog.search(
            self._context(env),
            EvidenceSearchRequest(
                query=question,
                kinds=(EvidenceKind.DOCUMENT,),
                max_results=16,
                max_total_bytes=64 * 1024,
                metadata={"document_coverage": "whole_short_document"},
            ),
        )

        self.assertEqual(len(batch.refs), source.chunk_count)
        self.assertEqual(
            [ref.citation["chunk"] for ref in batch.refs],
            list(range(1, source.chunk_count + 1)),
        )
        self.assertTrue(
            all(ref.citation["source_uuid"] == source.source_uuid for ref in batch.refs)
        )

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
            env_b["odoo.ai.knowledge.source"].lexical_search("private-only-marker-p9")
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
        self.assertEqual(
            turn.user_message_id.content, "Añade este archivo a Knowledge."
        )
        self.assertNotIn("odoo_ai_attachment", turn.user_message_id.content)
        self.assertIn("Host attachment references", turn.input_message)
        self.assertIn(f'"attachment_id":{attachment.id}', turn.input_message)
        self.assertEqual(attachment.turn_id.id, turn.id)
        self.assertEqual(
            turn.visible_knowledge_attachment_manifest(),
            [{"name": "chat-source.txt", "mimetype": "text/plain", "size": 21}],
        )

        history = env["odoo.ai.conversation"].history_payload(
            conversation_uuid=turn.conversation_id.conversation_uuid
        )
        user_row = next(item for item in history["messages"] if item["role"] == "user")
        self.assertEqual(user_row["attachments"][0]["name"], "chat-source.txt")

        attachment_catalog = EvidenceProviderCatalog(
            (build_turn_attachment_evidence_provider(),)
        )
        context = self._context(env, turn_id=turn.turn_uuid)
        batch = attachment_catalog.search(
            context,
            EvidenceSearchRequest(
                query=turn.input_message,
                kinds=(EvidenceKind.DOCUMENT,),
            ),
        )
        self.assertTrue(batch.refs)
        evidence_item = attachment_catalog.fetch(context, batch.refs[0])
        self.assertIn("chat-ingest-marker-p9", evidence_item.excerpt)
        self.assertEqual(batch.refs[0].citation["source_type"], "turn_attachment")

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
