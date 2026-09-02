from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

from odoo import Command
from odoo.tests.common import TransactionCase, tagged

from odoo.addons.odoo_ai_assistant.runtime.capabilities.contracts import (
    CapabilityError,
)
from odoo.addons.odoo_ai_assistant.runtime.capabilities.evidence import (
    EvidenceFreshness,
    EvidenceKind,
    EvidenceProviderCatalog,
    EvidenceSearchRequest,
)
from odoo.addons.odoo_ai_assistant.runtime.capabilities.runtime_evidence import (
    build_runtime_inventory_evidence_provider,
)


@tagged("post_install", "-at_install")
class TestPhase8RuntimeInventoryEvidence(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        company = cls.env.company
        cls.limited_user = cls.env["res.users"].create(
            {
                "name": "Phase 8 Evidence User",
                "login": "phase8-evidence-user",
                "company_id": company.id,
                "company_ids": [Command.set([company.id])],
                "groups_id": [Command.set([cls.env.ref("base.group_user").id])],
            }
        )

    def _context(
        self,
        *,
        env=None,
        user_id: int | None = None,
        technical_profile: str | None = None,
    ):
        env = env or self.env
        if technical_profile is None:
            technical_profile = (
                "technical"
                if env.user.has_group("base.group_system")
                else "user"
            )
        return SimpleNamespace(
            env=env,
            user_id=user_id or env.uid,
            company_ids=tuple(env.companies.ids),
            group_xmlids=(),
            technical_profile=technical_profile,
        )

    def test_inventory_search_fetch_and_access_recheck(self):
        context = self._context()
        catalog = EvidenceProviderCatalog(
            (build_runtime_inventory_evidence_provider(),)
        )
        batch = catalog.search(
            context,
            EvidenceSearchRequest(
                query="qué módulos hay instalados",
                kinds=(EvidenceKind.RUNTIME,),
            ),
        )

        self.assertEqual(len(batch.refs), 1)
        ref = batch.refs[0]
        item = catalog.fetch(context, ref)
        installed_names = {
            module["name"] for module in item.data["installed_modules"]
        }
        self.assertIn("odoo_ai_assistant", installed_names)
        self.assertEqual(item.ref.freshness, EvidenceFreshness.CURRENT)
        self.assertEqual(item.data["visibility"], "technical")
        self.assertNotIn("database_name", item.data)
        self.assertNotIn("addon_roots", item.data)

        denied_context = self._context(user_id=self.env.uid + 100000)
        with self.assertRaisesRegex(CapabilityError, "evidence_access_denied"):
            catalog.fetch(denied_context, ref)

    def test_inventory_is_available_to_normal_user_without_ir_module_acl(self):
        limited_env = self.env(user=self.limited_user, su=False)
        self.assertFalse(limited_env.su)
        self.assertFalse(limited_env.user.has_group("base.group_system"))
        context = self._context(env=limited_env)
        catalog = EvidenceProviderCatalog(
            (build_runtime_inventory_evidence_provider(),)
        )

        ref = catalog.search(
            context,
            EvidenceSearchRequest(
                query="qué módulos de Odoo están instalados",
                kinds=(EvidenceKind.RUNTIME,),
            ),
        ).refs[0]
        item = catalog.fetch(context, ref)

        installed_names = {
            module["name"] for module in item.data["installed_modules"]
        }
        self.assertIn("odoo_ai_assistant", installed_names)
        self.assertEqual(item.data["visibility"], "user")
        self.assertEqual(item.ref.access_scope.user_id, limited_env.uid)
        self.assertNotIn("addon_roots", item.data)
        self.assertNotIn("database_name", item.data)
        self.assertTrue(item.ref.metadata["host_metadata_read"])

    def test_fingerprint_mismatch_is_explicitly_stale(self):
        context = self._context()
        catalog = EvidenceProviderCatalog(
            (build_runtime_inventory_evidence_provider(),)
        )
        ref = catalog.search(
            context,
            EvidenceSearchRequest(
                query="installation version",
                kinds=(EvidenceKind.RUNTIME,),
            ),
        ).refs[0]

        stale_request = replace(ref, fingerprint="0" * 64)
        item = catalog.fetch(context, stale_request)

        self.assertEqual(item.ref.freshness, EvidenceFreshness.STALE)
        self.assertEqual(item.data["requested_fingerprint"], "0" * 64)
