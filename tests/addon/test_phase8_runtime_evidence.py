from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

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
    def _context(self, *, user_id: int | None = None):
        return SimpleNamespace(
            env=self.env,
            user_id=user_id or self.env.uid,
            company_ids=tuple(self.env.companies.ids),
            group_xmlids=(),
            technical_profile="technical",
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

        denied_context = self._context(user_id=self.env.uid + 100000)
        with self.assertRaisesRegex(CapabilityError, "evidence_access_denied"):
            catalog.fetch(denied_context, ref)

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
