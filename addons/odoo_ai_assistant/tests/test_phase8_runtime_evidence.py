from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

from odoo import Command
from odoo.addons.odoo_ai_assistant.runtime.capabilities.contracts import (
    CapabilityError,
)
from odoo.addons.odoo_ai_assistant.runtime.capabilities.evidence import (
    EvidenceFreshness,
    EvidenceKind,
    EvidenceProviderCatalog,
    EvidenceSearchRequest,
)
from odoo.addons.odoo_ai_assistant.runtime.capabilities.extensions import (
    discover_assistant_extensions_for_env,
)
from odoo.addons.odoo_ai_assistant.runtime.capabilities.registry import (
    discover_capabilities_for_env,
)
from odoo.addons.odoo_ai_assistant.runtime.capabilities.runtime_evidence import (
    build_runtime_inventory_evidence_provider,
)
from odoo.tests.common import TransactionCase, tagged


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

    def test_builtin_installed_source_and_log_providers_are_live(self):
        extensions = discover_assistant_extensions_for_env(
            self.env,
            capability_registry=discover_capabilities_for_env(self.env),
        )
        self.assertIn(
            "assistant.installed_source", extensions.evidence_providers.provider_ids
        )
        self.assertIn("assistant.odoo_log", extensions.evidence_providers.provider_ids)

        context = self._context()
        source_batch = extensions.evidence_providers.search(
            context,
            EvidenceSearchRequest(
                query=(
                    "odoo_ai_assistant_p7_fixture "
                    "phase8_hostile_fixture_marker python source"
                ),
                kinds=(EvidenceKind.SOURCE,),
                provider_ids=("assistant.installed_source",),
            ),
        )
        self.assertTrue(source_batch.refs)
        source_item = extensions.evidence_providers.fetch(
            context, source_batch.refs[0]
        )
        self.assertIn("phase8_hostile_fixture_marker", source_item.excerpt)
        self.assertEqual(
            source_item.ref.citation["module"], "odoo_ai_assistant_p7_fixture"
        )
        self.assertNotIn("/odoo/", repr(source_item.to_untrusted_projection()))
        self.assertEqual(
            source_item.to_untrusted_projection()["trust_boundary"],
            "untrusted_data",
        )

        log_batch = extensions.evidence_providers.search(
            context,
            EvidenceSearchRequest(
                query="TestPhase8RuntimeInventoryEvidence",
                kinds=(EvidenceKind.LOG,),
                provider_ids=("assistant.odoo_log",),
            ),
        )
        self.assertTrue(log_batch.refs)
        log_item = extensions.evidence_providers.fetch(context, log_batch.refs[0])
        self.assertIn("TestPhase8RuntimeInventoryEvidence", log_item.excerpt)
        self.assertNotIn("/tmp/p8", repr(log_item.ref.to_json_value()))
