from __future__ import annotations

from uuid import uuid4

from odoo import Command
from odoo.addons.odoo_ai_assistant.runtime.capabilities.contracts import (
    CapabilityContext,
)
from odoo.addons.odoo_ai_assistant.runtime.capabilities.registry import (
    discover_capabilities_for_env,
)
from odoo.addons.odoo_ai_assistant.runtime.source_workspace import (
    SourceWorkspaceError,
    delete_installed_module_workspace,
    inspect_installed_module_workspace,
    prepare_installed_module_workspace,
)
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestPhase12SourceWorkspace(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        technical = cls.env.ref("base.group_system")
        internal = cls.env.ref("base.group_user")
        cls.technical_user = cls.env["res.users"].create(
            {
                "name": "P12 Technical User",
                "login": "p12-technical-user",
                "company_id": cls.env.company.id,
                "company_ids": [Command.set([cls.env.company.id])],
                "groups_id": [Command.set([technical.id])],
            }
        )
        cls.other_technical_user = cls.env["res.users"].create(
            {
                "name": "P12 Other Technical User",
                "login": "p12-other-technical-user",
                "company_id": cls.env.company.id,
                "company_ids": [Command.set([cls.env.company.id])],
                "groups_id": [Command.set([technical.id])],
            }
        )
        cls.normal_user = cls.env["res.users"].create(
            {
                "name": "P12 Normal User",
                "login": "p12-normal-user",
                "company_id": cls.env.company.id,
                "company_ids": [Command.set([cls.env.company.id])],
                "groups_id": [Command.set([internal.id])],
            }
        )

    def _context(self, user, *, turn_id=None):
        return CapabilityContext(
            env=self.env(user=user, su=False),
            turn_id=turn_id or str(uuid4()),
        )

    def test_technical_user_prepares_path_free_installed_addon_workspace(self):
        context = self._context(self.technical_user)
        receipt = prepare_installed_module_workspace(context, "odoo_ai_assistant")
        try:
            public = receipt.public_metadata()
            self.assertEqual(public["module"], "odoo_ai_assistant")
            self.assertEqual(public["source_id"], "odoo-addon:odoo_ai_assistant")
            self.assertFalse(public["source_stale"])
            self.assertFalse(public["workspace_changed"])
            self.assertGreater(public["file_count"], 0)
            self.assertEqual(public["file_count"], public["current_file_count"])
            self.assertNotIn("workspace_path", public)
            self.assertNotIn("addons_path", public)
            self.assertNotIn("data_dir", public)
            self.assertNotIn(context.env.cr.dbname, repr(public))
            self.assertNotIn("/odoo/", repr(public))

            checked = inspect_installed_module_workspace(context, receipt.workspace_id)
            self.assertEqual(
                checked.current_workspace_fingerprint,
                receipt.current_workspace_fingerprint,
            )
            self.assertEqual(checked.binding_fingerprint, receipt.binding_fingerprint)

            # P12.2 may expose typed capabilities through its provider, but the P12.1
            # workspace primitive itself remains a non-decorated host utility rather than a
            # second executable registry.
            registry = discover_capabilities_for_env(context.env)
            self.assertFalse(
                any(
                    definition.source_module.endswith(".runtime.source_workspace")
                    for definition in registry.definitions
                )
            )
            available = {item.name for item in registry.available(context)}
            self.assertIn("assistant.source_workspace.prepare", available)
            self.assertIn("assistant.source_workspace.inspect", available)
        finally:
            delete_installed_module_workspace(context, receipt.workspace_id)

    def test_non_technical_user_cannot_prepare_workspace(self):
        context = self._context(self.normal_user)
        with self.assertRaisesRegex(
            SourceWorkspaceError,
            "source_workspace_technical_required",
        ):
            prepare_installed_module_workspace(context, "odoo_ai_assistant")

    def test_workspace_binding_is_turn_and_user_scoped(self):
        turn_id = str(uuid4())
        owner = self._context(self.technical_user, turn_id=turn_id)
        receipt = prepare_installed_module_workspace(owner, "odoo_ai_assistant")
        try:
            other_user = self._context(self.other_technical_user, turn_id=turn_id)
            with self.assertRaisesRegex(
                SourceWorkspaceError,
                "source_workspace_binding_mismatch",
            ):
                inspect_installed_module_workspace(other_user, receipt.workspace_id)

            other_turn = self._context(self.technical_user)
            with self.assertRaisesRegex(
                SourceWorkspaceError,
                "source_workspace_binding_mismatch",
            ):
                inspect_installed_module_workspace(other_turn, receipt.workspace_id)
        finally:
            delete_installed_module_workspace(owner, receipt.workspace_id)
