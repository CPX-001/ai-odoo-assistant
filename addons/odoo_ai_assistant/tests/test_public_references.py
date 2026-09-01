from uuid import uuid4

from odoo import SUPERUSER_ID, Command
from odoo.tests import TransactionCase, tagged

from ..runtime.capabilities import CapabilityContext
from ..runtime.capabilities.providers.odoo_navigation import (
    _matches_specific_query_terms,
    resolve_navigation,
)


@tagged("post_install", "-at_install")
class TestAssistantPublicReferences(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        internal = cls.env.ref("base.group_user")
        settings = cls.env.ref("base.group_system")
        cls.reference_user = cls.env["res.users"].create(
            {
                "name": "AI Reference User",
                "login": "ai-reference-user",
                "groups_id": [Command.set([internal.id, settings.id])],
                "company_id": cls.env.company.id,
                "company_ids": [Command.set([cls.env.company.id])],
            }
        )
        cls.normal_reference_user = cls.env["res.users"].create(
            {
                "name": "AI Normal Reference User",
                "login": "ai-normal-reference-user",
                "groups_id": [Command.set([internal.id])],
                "company_id": cls.env.company.id,
                "company_ids": [Command.set([cls.env.company.id])],
            }
        )
        cls.partner = cls.env["res.partner"].create(
            {"name": "Reference Acme", "ref": "REF-ACME"}
        )
        cls.action = cls.env["ir.actions.act_window"].create(
            {
                "name": "AI Reference Contacts",
                "res_model": "res.partner",
                "view_mode": "list,form",
            }
        )
        cls.settings_action = cls.env["ir.actions.act_window"].create(
            {
                "name": "AI Reference Settings",
                "res_model": "res.config.settings",
                "view_mode": "form",
            }
        )
        cls.menu = cls.env["ir.ui.menu"].create(
            {
                "name": "AI Reference Contacts Menu",
                "action": f"ir.actions.act_window,{cls.action.id}",
            }
        )
        cls.view = cls.env.ref("base.view_partner_tree")

    def _resolver(self):
        return self.env["odoo.ai.user.preference"].with_user(self.reference_user)

    def _user_env(self):
        return self.env(user=self.reference_user, su=False)

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
        self.assertEqual(
            reference["navigation"],
            {"mode": "record", "model": "res.partner", "record_id": self.partner.id},
        )
        self.assertLessEqual(len(reference["fields"]), 3)
        self.assertTrue(
            all(set(field) == {"name", "label", "value"} for field in reference["fields"])
        )

    def test_verified_effect_receipt_projects_effective_user_record_reference(self):
        turn = self.env["odoo.ai.turn"].with_user(SUPERUSER_ID).create(
            {
                "turn_uuid": str(uuid4()),
                "user_id": self.reference_user.id,
                "company_id": self.env.company.id,
                "state": "running",
                "input_message": "Update and show the contact reference",
                "allowed_company_ids": [self.env.company.id],
                "attempt_count": 1,
                "max_attempts": 1,
            }
        )

        references = turn._capture_public_navigation_references(
            [
                {
                    "kind": "verified_effect_receipt",
                    "data": {
                        "verified": True,
                        "steps": [
                            {
                                "result": {
                                    "model": "res.partner",
                                    "record_id": self.partner.id,
                                }
                            }
                        ],
                    },
                }
            ]
        )

        self.assertEqual(
            references,
            [
                {
                    "kind": "odoo_record",
                    "model": "res.partner",
                    "record_id": self.partner.id,
                    "label": "Reference Acme",
                }
            ],
        )
        self.assertEqual(turn.public_reference_payload, references)

    def test_model_action_view_menu_and_setting_are_closed_and_revalidated(self):
        requests = [
            {"kind": "odoo_model", "model": "res.partner"},
            {"kind": "odoo_action", "action_id": self.action.id},
            {"kind": "odoo_view", "view_id": self.view.id},
            {"kind": "odoo_menu", "menu_id": self.menu.id},
            {
                "kind": "odoo_setting",
                "action_id": self.settings_action.id,
                "setting_field": "company_id",
            },
        ]

        result = self._resolver().resolve_public_references(requests)

        self.assertTrue(result["ok"])
        self.assertEqual(
            [row["reference"]["kind"] for row in result["references"] if row["ok"]],
            ["odoo_model", "odoo_action", "odoo_view", "odoo_menu", "odoo_setting"],
        )
        self.assertTrue(all(row["ok"] for row in result["references"]))
        action = result["references"][1]["reference"]
        self.assertEqual(action["navigation"], {"mode": "action", "action_id": self.action.id})
        view = result["references"][2]["reference"]
        self.assertEqual(view["navigation"]["mode"], "view")
        self.assertEqual(view["navigation"]["view_id"], self.view.id)
        menu = result["references"][3]["reference"]
        self.assertEqual(menu["menu_id"], self.menu.id)
        setting = result["references"][4]["reference"]
        self.assertEqual(setting["model"], "res.config.settings")
        self.assertEqual(setting["setting_field"], "company_id")

    def test_malformed_reference_and_additional_keys_fail_closed(self):
        result = self._resolver().resolve_public_references(
            [
                {"kind": "odoo_action", "action_id": -1},
                {"kind": "odoo_action", "action_id": self.action.id, "route": "/web#unsafe"},
                {
                    "kind": "odoo_setting",
                    "action_id": self.settings_action.id,
                    "setting_field": "company_id",
                    "model": "res.config.settings",
                },
            ]
        )
        self.assertTrue(result["ok"])
        self.assertEqual(
            [row["error"]["code"] for row in result["references"]],
            ["reference_unavailable", "reference_unavailable", "reference_unavailable"],
        )

    def test_missing_or_deleted_reference_fails_closed_per_item(self):
        action = self.env["ir.actions.act_window"].create(
            {
                "name": "Deleted AI Reference",
                "res_model": "res.partner",
                "view_mode": "list,form",
            }
        )
        action_id = action.id
        action.unlink()
        result = self._resolver().resolve_public_references(
            [
                {
                    "kind": "odoo_record",
                    "model": "res.partner",
                    "record_id": 2_147_483_647,
                },
                {"kind": "odoo_action", "action_id": action_id},
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
                "groups": [Command.set([self.env.ref("base.group_user").id])],
                "perm_read": True,
                "perm_write": False,
                "perm_create": False,
                "perm_unlink": False,
            }
        )

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

    def test_menu_becomes_unavailable_when_current_group_visibility_revokes_it(self):
        hidden_group = self.env["res.groups"].create({"name": "AI hidden navigation group"})
        self.menu.write({"groups_id": [Command.set([hidden_group.id])]})
        result = self._resolver().resolve_public_references(
            [{"kind": "odoo_menu", "menu_id": self.menu.id}]
        )
        self.assertFalse(result["references"][0]["ok"])
        self.assertEqual(result["references"][0]["error"]["code"], "reference_unavailable")

    def test_resolve_navigation_discovers_host_resolved_references_without_sudo(self):
        env = self._user_env()
        context = CapabilityContext(env=env, turn_id="navigation-turn-0001")

        result = resolve_navigation(
            context,
            {"query": "AI Reference Contacts", "kinds": ["odoo_action", "odoo_menu"], "limit": 8},
        )

        self.assertFalse(env.su)
        self.assertTrue(result["references"])
        self.assertTrue(
            all(item["kind"] in {"odoo_action", "odoo_menu"} for item in result["references"])
        )
        self.assertTrue(
            any(item.get("action_id") == self.action.id for item in result["references"])
        )
        self.assertTrue(all("route" not in item and "url" not in item for item in result["references"]))

    def test_visible_menu_navigation_works_without_settings_metadata_acl(self):
        env = self.env(user=self.normal_reference_user, su=False)
        context = CapabilityContext(env=env, turn_id="navigation-turn-normal-user")

        discovered = resolve_navigation(
            context,
            {"query": "AI Reference Contacts", "kinds": ["odoo_action", "odoo_menu"]},
        )
        resolved = env["odoo.ai.user.preference"].resolve_public_references(
            [{"kind": "odoo_menu", "menu_id": self.menu.id}]
        )

        self.assertFalse(env.su)
        self.assertTrue(discovered["references"])
        self.assertTrue(resolved["references"][0]["ok"])

    def test_resolve_navigation_finds_installed_configuration_option(self):
        env = self._user_env()
        context = CapabilityContext(env=env, turn_id="navigation-turn-0002")
        label = env["res.config.settings"].fields_get(
            allfields=["company_id"], attributes=["string"]
        )["company_id"]["string"]

        result = resolve_navigation(
            context,
            {"query": label, "kinds": ["odoo_setting"], "limit": 8},
        )

        self.assertTrue(result["references"])
        self.assertTrue(
            any(
                item["kind"] == "odoo_setting" and item["setting_field"] == "company_id"
                for item in result["references"]
            )
        )

    def test_navigation_drops_results_matching_only_generic_configuration_wording(self):
        irrelevant = {
            "kind": "odoo_menu",
            "label": "Contact tags",
            "description": "Visible menu in Configuration",
            "model": "res.partner.category",
        }

        self.assertFalse(
            _matches_specific_query_terms("configuración de impuestos", irrelevant)
        )
        self.assertTrue(
            _matches_specific_query_terms(
                "configuración de impuestos",
                {**irrelevant, "label": "Impuestos"},
            )
        )
