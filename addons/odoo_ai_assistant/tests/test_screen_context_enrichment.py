from datetime import UTC, datetime

from odoo.tests.common import TransactionCase

from ..services.screen_context import enrich_runtime_screen, validate_query_screen


class TestScreenContextEnrichment(TransactionCase):
    def test_query_screen_accepts_current_view_only_as_bounded_hint(self):
        captured = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)
        parsed = validate_query_screen(
            {
                "action_id": 42,
                "menu_id": 7,
                "view_id": 314,
                "view_type": "form",
                "model": "res.partner",
                "res_id": None,
                "selected_ids": [],
                "allowed_context_subset": {},
                "captured_at": captured.isoformat().replace("+00:00", "Z"),
            },
            clock=lambda: captured,
        )

        self.assertEqual(parsed.view_id, 314)
        self.assertEqual(parsed.to_mapping()["view_id"], 314)

    def test_resolved_view_projects_labels_not_raw_architecture(self):
        view = self.env["ir.ui.view"].create(
            {
                "name": "AI custom partner context",
                "model": "res.partner",
                "type": "form",
                "arch": """
                    <form string="Custom partner workspace">
                        <sheet>
                            <notebook>
                                <page string="Custom insights">
                                    <field name="name"/>
                                    <field name="email"/>
                                </page>
                            </notebook>
                        </sheet>
                    </form>
                """,
            }
        )
        effective_env = self.env(user=self.env.user, su=False)

        enriched = enrich_runtime_screen(
            effective_env,
            {
                "model": "res.partner",
                "view_id": view.id,
                "view_type": "form",
                "res_id": None,
                "selected_ids": [],
                "allowed_context_subset": {},
            },
        )

        self.assertEqual(enriched["view_label"], "AI custom partner context")
        self.assertIn("Custom insights", enriched["view_sections"])
        self.assertIn("Name", enriched["view_fields"])
        self.assertIn("Email", enriched["view_fields"])
        self.assertNotIn("arch", enriched)
        self.assertNotIn("xml", enriched)

    def test_mismatched_model_view_is_not_used_as_context(self):
        view = self.env["ir.ui.view"].create(
            {
                "name": "AI partner-only view",
                "model": "res.partner",
                "type": "form",
                "arch": '<form><field name="name"/></form>',
            }
        )
        effective_env = self.env(user=self.env.user, su=False)

        enriched = enrich_runtime_screen(
            effective_env,
            {
                "model": "sale.order",
                "view_id": view.id,
                "view_type": "form",
            },
        )

        self.assertNotIn("view_label", enriched)
        self.assertNotIn("view_fields", enriched)
        self.assertNotIn("view_sections", enriched)
