from odoo import Command
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestAssistantPublicReferences(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        internal = cls.env.ref("base.group_user")
        cls.reference_user = cls.env["res.users"].create(
            {
                "name": "AI Reference User",
                "login": "ai-reference-user",
                "groups_id": [Command.set([internal.id])],
                "company_id": cls.env.company.id,
                "company_ids": [Command.set([cls.env.company.id])],
            }
        )
        cls.partner = cls.env["res.partner"].create(
            {"name": "Reference Acme", "ref": "REF-ACME"}
        )

    def _resolver(self):
        return self.env["odoo.ai.user.preference"].with_user(self.reference_user)

    def test_record_reference_is_revalidated_under_effective_user(self):
        resolver = self._resolver()
        self.assertFalse(resolver.env.su)

        result = resolver.resolve_public_references(
            [
                {
                    "kind": "odoo_record",
                    "model": "res.partner",
                    "record_id": self.partner.id,
                }
            ]
        )

        self.assertTrue(result["ok"])
        row = result["references"][0]
        self.assertTrue(row["ok"])
        reference = row["reference"]
        self.assertEqual(reference["kind"], "odoo_record")
        self.assertEqual(reference["model"], "res.partner")
        self.assertEqual(reference["record_id"], self.partner.id)
        self.assertEqual(reference["label"], "Reference Acme")
        self.assertEqual(reference["navigation"], {"view_type": "form"})
        self.assertLessEqual(len(reference["fields"]), 3)
        self.assertTrue(
            all(set(field) == {"name", "label", "value"} for field in reference["fields"])
        )

    def test_missing_or_malformed_reference_fails_closed_per_item(self):
        result = self._resolver().resolve_public_references(
            [
                {
                    "kind": "odoo_record",
                    "model": "res.partner",
                    "record_id": 2_147_483_647,
                },
                {"kind": "odoo_record", "model": "res.partner", "record_id": -1},
            ]
        )

        self.assertTrue(result["ok"])
        self.assertEqual(
            [row["error"]["code"] for row in result["references"]],
            ["reference_unavailable", "reference_unavailable"],
        )

    def test_reference_disappears_when_record_rule_revokes_access(self):
        resolver = self._resolver()
        before = resolver.resolve_public_references(
            [
                {
                    "kind": "odoo_record",
                    "model": "res.partner",
                    "record_id": self.partner.id,
                }
            ]
        )
        self.assertTrue(before["references"][0]["ok"])

        self.env["ir.rule"].create(
            {
                "name": "AI reference deny test",
                "model_id": self.env["ir.model"]._get_id("res.partner"),
                "domain_force": "[('id', '=', 0)]",
                "perm_read": True,
                "perm_write": False,
                "perm_create": False,
                "perm_unlink": False,
            }
        )
        self.env.registry.clear_cache()

        after = resolver.resolve_public_references(
            [
                {
                    "kind": "odoo_record",
                    "model": "res.partner",
                    "record_id": self.partner.id,
                }
            ]
        )
        self.assertFalse(after["references"][0]["ok"])
        self.assertEqual(after["references"][0]["error"]["code"], "reference_unavailable")
