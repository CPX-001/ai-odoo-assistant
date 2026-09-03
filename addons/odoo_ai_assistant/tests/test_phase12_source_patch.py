from __future__ import annotations

from uuid import uuid4

from odoo import Command
from odoo.addons.odoo_ai_assistant.runtime.capabilities import (
    CapabilityApproval,
    CapabilityContext,
    CapabilityEffect,
    CapabilityError,
    CapabilityExposure,
    CapabilityRisk,
    clear_discovery_cache,
    discover_capabilities_for_env,
)
from odoo.addons.odoo_ai_assistant.runtime.capabilities.providers.technical_source_workspace import (
    apply_patch,
    inspect_patch,
    preview_patch,
    read_workspace_file,
)
from odoo.addons.odoo_ai_assistant.runtime.capabilities.source_evidence import (
    _odoo_module_roots,
)
from odoo.addons.odoo_ai_assistant.runtime.source_workspace import (
    delete_installed_module_workspace,
    prepare_installed_module_workspace,
)
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestPhase12SourcePatch(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        company = cls.env.company
        technical = cls.env.ref("base.group_system")
        internal = cls.env.ref("base.group_user")
        cls.technical_user = cls.env["res.users"].create(
            {
                "name": "P12 Patch Technical User",
                "login": "p12-patch-technical-user",
                "company_id": company.id,
                "company_ids": [Command.set([company.id])],
                "groups_id": [Command.set([internal.id, technical.id])],
            }
        )
        cls.other_technical_user = cls.env["res.users"].create(
            {
                "name": "P12 Patch Other Technical User",
                "login": "p12-patch-other-technical-user",
                "company_id": company.id,
                "company_ids": [Command.set([company.id])],
                "groups_id": [Command.set([internal.id, technical.id])],
            }
        )
        cls.normal_user = cls.env["res.users"].create(
            {
                "name": "P12 Patch Normal User",
                "login": "p12-patch-normal-user",
                "company_id": company.id,
                "company_ids": [Command.set([company.id])],
                "groups_id": [Command.set([internal.id])],
            }
        )

    def setUp(self):
        super().setUp()
        clear_discovery_cache()

    def _context(self, user, *, turn_id=None):
        env = self.env(user=user, su=False)
        self.assertFalse(env.su)
        return CapabilityContext(env=env, turn_id=turn_id or str(uuid4()))

    def test_source_patch_capabilities_are_technical_and_plan_bound(self):
        technical = self._context(self.technical_user)
        normal = self._context(self.normal_user)
        registry = discover_capabilities_for_env(technical.env)
        technical_available = {item.name for item in registry.available(technical)}
        normal_available = {item.name for item in registry.available(normal)}
        names = {
            "assistant.source_workspace.prepare",
            "assistant.source_workspace.inspect",
            "assistant.source_workspace.read_file",
            "assistant.source_workspace.preview_patch",
            "assistant.source_workspace.apply_patch",
            "assistant.source_workspace.inspect_patch",
        }
        self.assertTrue(names.issubset(technical_available))
        self.assertFalse(names.intersection(normal_available))

        prepare = registry.resolve("assistant.source_workspace.prepare")
        self.assertEqual(prepare.risk, CapabilityRisk.ACTION_PREVIEW)
        self.assertEqual(prepare.effect, CapabilityEffect.INTERNAL_REVERSIBLE)
        self.assertEqual(prepare.exposure, CapabilityExposure.PLAN)
        self.assertEqual(prepare.required_groups, ("base.group_system",))
        self.assertIsNotNone(prepare.preview_handler)
        self.assertIsNotNone(prepare.verify_handler)

        patch = registry.resolve("assistant.source_workspace.apply_patch")
        self.assertEqual(patch.risk, CapabilityRisk.ACTION)
        self.assertEqual(patch.effect, CapabilityEffect.INTERNAL_REVERSIBLE)
        self.assertEqual(patch.exposure, CapabilityExposure.PLAN)
        self.assertEqual(patch.approval, CapabilityApproval.POLICY)
        self.assertEqual(patch.required_groups, ("base.group_system",))
        self.assertIsNotNone(patch.preview_handler)
        self.assertIsNotNone(patch.verify_handler)
        self.assertEqual(patch.audit_metadata["recovery_mode"], "segmented")
        self.assertEqual(
            patch.audit_metadata["journal_classification"],
            "reconstructable",
        )

    def test_patch_creates_derived_workspace_and_never_mutates_installed_source(self):
        context = self._context(self.technical_user)
        source_root = _odoo_module_roots(context)["odoo_ai_assistant"]
        source_readme = source_root / "README.md"
        source_before = source_readme.read_bytes()
        parent = prepare_installed_module_workspace(context, "odoo_ai_assistant")
        child_id = None
        try:
            read = read_workspace_file(
                context,
                {
                    "workspace_id": parent.workspace_id,
                    "logical_path": "README.md",
                    "start_line": 1,
                    "max_lines": 20,
                },
            )
            self.assertIn("# Odoo AI Assistant addon", read["text"])
            changes = [
                {
                    "path": "README.md",
                    "action": "modify",
                    "edits": [
                        {
                            "old": "# Odoo AI Assistant addon",
                            "new": "# Odoo AI Assistant addon (P12 staged fixture)",
                        }
                    ],
                }
            ]
            arguments = {
                "workspace_id": parent.workspace_id,
                "expected_workspace_fingerprint": parent.current_workspace_fingerprint,
                "changes": changes,
            }
            preview = preview_patch(context, arguments)
            self.assertIn("before/README.md", preview["diff"])
            self.assertIn("after/README.md", preview["diff"])
            self.assertEqual(source_readme.read_bytes(), source_before)

            applied = apply_patch(context, arguments)
            child_id = applied["workspace_id"]
            self.assertEqual(applied["parent_workspace_id"], parent.workspace_id)
            self.assertEqual(
                applied["before_workspace_fingerprint"],
                parent.current_workspace_fingerprint,
            )
            self.assertEqual(
                applied["diff_fingerprint"],
                preview["diff_fingerprint"],
            )
            self.assertEqual(
                applied["approval_fingerprint"],
                preview["approval_fingerprint"],
            )
            receipt = inspect_patch(context, {"workspace_id": child_id})
            self.assertEqual(receipt["diff_fingerprint"], preview["diff_fingerprint"])

            child = read_workspace_file(
                context,
                {
                    "workspace_id": child_id,
                    "logical_path": "README.md",
                    "start_line": 1,
                    "max_lines": 20,
                },
            )
            self.assertIn("P12 staged fixture", child["text"])
            parent_after = read_workspace_file(
                context,
                {
                    "workspace_id": parent.workspace_id,
                    "logical_path": "README.md",
                    "start_line": 1,
                    "max_lines": 20,
                },
            )
            self.assertNotIn("P12 staged fixture", parent_after["text"])
            self.assertEqual(source_readme.read_bytes(), source_before)
        finally:
            if child_id:
                delete_installed_module_workspace(context, child_id)
            delete_installed_module_workspace(context, parent.workspace_id)

    def test_patch_rejects_stale_workspace_and_cross_binding(self):
        owner = self._context(self.technical_user)
        parent = prepare_installed_module_workspace(owner, "odoo_ai_assistant")
        try:
            arguments = {
                "workspace_id": parent.workspace_id,
                "expected_workspace_fingerprint": parent.current_workspace_fingerprint,
                "changes": [
                    {
                        "path": "README.md",
                        "action": "modify",
                        "edits": [
                            {
                                "old": "# Odoo AI Assistant addon",
                                "new": "# Odoo AI Assistant addon (staged)",
                            }
                        ],
                    }
                ],
            }
            other_turn = self._context(self.technical_user)
            with self.assertRaisesRegex(
                CapabilityError,
                "source_workspace_binding_mismatch",
            ):
                preview_patch(other_turn, arguments)

            other_user = self._context(
                self.other_technical_user,
                turn_id=owner.turn_id,
            )
            with self.assertRaisesRegex(
                CapabilityError,
                "source_workspace_binding_mismatch",
            ):
                preview_patch(other_user, arguments)

            staged = parent.workspace_path / "README.md"
            staged.write_text(staged.read_text() + "\nP12 local staged change\n")
            with self.assertRaisesRegex(
                CapabilityError,
                "source_patch_workspace_stale",
            ):
                preview_patch(owner, arguments)
        finally:
            delete_installed_module_workspace(owner, parent.workspace_id)
