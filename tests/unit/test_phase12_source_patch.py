from __future__ import annotations

import shutil
import stat
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "addons" / "odoo_ai_assistant" / "runtime"))

from source_patch import SourcePatchError, SourcePatchStore
from source_workspace import SourceWorkspaceStore


class SourcePatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / "installed" / "fixture_addon"
        self.workspace_root = self.root / "runtime" / "workspaces"
        (self.source / "models").mkdir(parents=True)
        (self.source / "views").mkdir()
        (self.source / "models" / "sale.py").write_text(
            "class SaleOrder:\n    marker = 'before'\n"
        )
        (self.source / "views" / "sale.xml").write_text(
            "<odoo><record id=\"old\"/></odoo>\n"
        )
        (self.source / "__manifest__.py").write_text("{'name': 'Fixture'}\n")
        self.store = SourceWorkspaceStore(self.workspace_root).ensure()
        self.patch_store = SourcePatchStore(self.store)
        self.binding = {
            "odoo_uid": 7,
            "company_id": 3,
            "database_fingerprint": "sha256:" + "d" * 64,
            "turn_id": "turn-test-0001",
        }
        self.workspace = self.store.prepare(
            module="fixture_addon",
            source_root=self.source,
            binding=self.binding,
        )

    def tearDown(self):
        self.temp.cleanup()

    def _changes(self):
        return [
            {
                "path": "models/sale.py",
                "action": "modify",
                "edits": [
                    {"old": "marker = 'before'", "new": "marker = 'after'"}
                ],
            }
        ]

    def test_preview_is_deterministic_and_does_not_mutate_parent(self):
        parent_before = (self.workspace.workspace_path / "models" / "sale.py").read_bytes()
        first = self.patch_store.preview(
            workspace_id=self.workspace.workspace_id,
            expected_workspace_fingerprint=self.workspace.current_workspace_fingerprint,
            changes=self._changes(),
            binding=self.binding,
            source_root=self.source,
        )
        second = self.patch_store.preview(
            workspace_id=self.workspace.workspace_id,
            expected_workspace_fingerprint=self.workspace.current_workspace_fingerprint,
            changes=self._changes(),
            binding=self.binding,
            source_root=self.source,
        )
        self.assertEqual(first.diff, second.diff)
        self.assertEqual(first.diff_fingerprint, second.diff_fingerprint)
        self.assertEqual(first.approval_fingerprint, second.approval_fingerprint)
        self.assertEqual(
            first.after_workspace_fingerprint,
            second.after_workspace_fingerprint,
        )
        self.assertNotEqual(
            first.before_workspace_fingerprint,
            first.after_workspace_fingerprint,
        )
        self.assertIn("before/models/sale.py", first.diff)
        self.assertIn("after/models/sale.py", first.diff)
        self.assertNotIn(str(self.workspace.workspace_path), first.diff)
        self.assertEqual(
            (self.workspace.workspace_path / "models" / "sale.py").read_bytes(),
            parent_before,
        )

    def test_apply_creates_derived_workspace_and_preserves_parent(self):
        parent_before = (self.workspace.workspace_path / "models" / "sale.py").read_text()
        receipt = self.patch_store.apply(
            workspace_id=self.workspace.workspace_id,
            expected_workspace_fingerprint=self.workspace.current_workspace_fingerprint,
            changes=self._changes(),
            binding=self.binding,
            source_root=self.source,
        )
        self.assertNotEqual(receipt.workspace_id, self.workspace.workspace_id)
        self.assertEqual(receipt.parent_workspace_id, self.workspace.workspace_id)
        self.assertEqual(
            (self.workspace.workspace_path / "models" / "sale.py").read_text(),
            parent_before,
        )
        self.assertIn(
            "marker = 'after'",
            (receipt.workspace_path / "models" / "sale.py").read_text(),
        )
        self.assertEqual(
            receipt.after_workspace_fingerprint,
            self.store.inspect(
                receipt.workspace_id,
                binding=self.binding,
            ).current_workspace_fingerprint,
        )
        inspected = self.patch_store.inspect_receipt(
            receipt.workspace_id,
            binding=self.binding,
            source_root=self.source,
        )
        self.assertEqual(inspected.diff_fingerprint, receipt.diff_fingerprint)
        self.assertEqual(
            inspected.approval_fingerprint,
            receipt.approval_fingerprint,
        )

    def test_create_delete_and_modify_are_typed_and_logical(self):
        changes = [
            {
                "path": "models/sale.py",
                "action": "modify",
                "edits": [{"old": "'before'", "new": "'after'"}],
            },
            {
                "path": "models/new_model.py",
                "action": "create",
                "content": "VALUE = 1\n",
            },
            {"path": "views/sale.xml", "action": "delete"},
        ]
        preview = self.patch_store.preview(
            workspace_id=self.workspace.workspace_id,
            expected_workspace_fingerprint=self.workspace.current_workspace_fingerprint,
            changes=changes,
            binding=self.binding,
            source_root=self.source,
        )
        self.assertEqual(preview.change_count, 3)
        self.assertEqual(
            [item["path"] for item in preview.changed_files],
            ["models/new_model.py", "models/sale.py", "views/sale.xml"],
        )
        self.assertIn("after/models/new_model.py", preview.diff)
        self.assertIn("before/views/sale.xml", preview.diff)

    def test_stale_workspace_or_installed_source_fails_closed(self):
        with self.assertRaisesRegex(SourcePatchError, "source_patch_workspace_stale"):
            self.patch_store.preview(
                workspace_id=self.workspace.workspace_id,
                expected_workspace_fingerprint="sha256:" + "a" * 64,
                changes=self._changes(),
                binding=self.binding,
                source_root=self.source,
            )

        (self.source / "views" / "sale.xml").write_text("<odoo><record/></odoo>\n")
        with self.assertRaisesRegex(SourcePatchError, "source_patch_source_stale"):
            self.patch_store.preview(
                workspace_id=self.workspace.workspace_id,
                expected_workspace_fingerprint=self.workspace.current_workspace_fingerprint,
                changes=self._changes(),
                binding=self.binding,
                source_root=self.source,
            )

    def test_path_secret_vcs_and_binary_boundaries_fail_closed(self):
        invalid = (
            (
                {"path": "../escape.py", "action": "create", "content": "x=1\n"},
                "source_patch_path_invalid",
            ),
            (
                {"path": "/tmp/escape.py", "action": "create", "content": "x=1\n"},
                "source_patch_path_invalid",
            ),
            (
                {"path": ".env", "action": "create", "content": "SECRET=1\n"},
                "source_patch_path_not_allowed",
            ),
            (
                {"path": ".git/config", "action": "create", "content": "x\n"},
                "source_patch_path_not_allowed",
            ),
            (
                {"path": "models/data.bin", "action": "create", "content": "x\n"},
                "source_patch_path_not_allowed",
            ),
        )
        for change, code in invalid:
            with self.subTest(path=change["path"]), self.assertRaisesRegex(
                SourcePatchError,
                code,
            ):
                self.patch_store.preview(
                    workspace_id=self.workspace.workspace_id,
                    expected_workspace_fingerprint=self.workspace.current_workspace_fingerprint,
                    changes=[change],
                    binding=self.binding,
                    source_root=self.source,
                )

        (self.workspace.workspace_path / "models" / "binary.py").write_bytes(
            b"\xff\xfe\x00"
        )
        changed = self.store.inspect(self.workspace.workspace_id, binding=self.binding)
        with self.assertRaisesRegex(SourcePatchError, "source_patch_file_not_text"):
            self.patch_store.preview(
                workspace_id=self.workspace.workspace_id,
                expected_workspace_fingerprint=changed.current_workspace_fingerprint,
                changes=[
                    {
                        "path": "models/binary.py",
                        "action": "modify",
                        "edits": [{"old": "x", "new": "y"}],
                    }
                ],
                binding=self.binding,
            )

    def test_modify_requires_one_exact_current_match(self):
        for old in ("missing text", "a"):
            with self.subTest(old=old), self.assertRaisesRegex(
                SourcePatchError,
                "source_patch_match_not_unique",
            ):
                self.patch_store.preview(
                    workspace_id=self.workspace.workspace_id,
                    expected_workspace_fingerprint=self.workspace.current_workspace_fingerprint,
                    changes=[
                        {
                            "path": "models/sale.py",
                            "action": "modify",
                            "edits": [{"old": old, "new": "replacement"}],
                        }
                    ],
                    binding=self.binding,
                    source_root=self.source,
                )

    def test_binding_cannot_be_transferred(self):
        other = dict(self.binding, turn_id="turn-test-0002")
        with self.assertRaisesRegex(
            SourcePatchError,
            "source_workspace_binding_mismatch",
        ):
            self.patch_store.preview(
                workspace_id=self.workspace.workspace_id,
                expected_workspace_fingerprint=self.workspace.current_workspace_fingerprint,
                changes=self._changes(),
                binding=other,
                source_root=self.source,
            )
        receipt = self.patch_store.apply(
            workspace_id=self.workspace.workspace_id,
            expected_workspace_fingerprint=self.workspace.current_workspace_fingerprint,
            changes=self._changes(),
            binding=self.binding,
            source_root=self.source,
        )
        with self.assertRaisesRegex(
            SourcePatchError,
            "source_workspace_binding_mismatch",
        ):
            self.patch_store.inspect_receipt(
                receipt.workspace_id,
                binding=other,
                source_root=self.source,
            )

    def test_derived_workspace_or_receipt_tamper_is_detected(self):
        receipt = self.patch_store.apply(
            workspace_id=self.workspace.workspace_id,
            expected_workspace_fingerprint=self.workspace.current_workspace_fingerprint,
            changes=self._changes(),
            binding=self.binding,
            source_root=self.source,
        )
        staged = receipt.workspace_path / "models" / "sale.py"
        staged.write_text("tampered = True\n")
        with self.assertRaisesRegex(SourcePatchError, "source_patch_receipt_invalid"):
            self.patch_store.inspect_receipt(
                receipt.workspace_id,
                binding=self.binding,
                source_root=self.source,
            )

    def test_diff_limit_rejects_approval_truncation(self):
        large = (
            "\n".join(
                f"line-{index:04d}-aaaaaaaaaaaaaaaa" for index in range(1500)
            )
            + "\n"
        )
        path = self.workspace.workspace_path / "models" / "large.py"
        path.write_text(large)
        current = self.store.inspect(self.workspace.workspace_id, binding=self.binding)
        replacement = (
            "\n".join(
                f"line-{index:04d}-bbbbbbbbbbbbbbbb" for index in range(1500)
            )
            + "\n"
        )
        with self.assertRaisesRegex(SourcePatchError, "source_patch_diff_too_large"):
            self.patch_store.preview(
                workspace_id=self.workspace.workspace_id,
                expected_workspace_fingerprint=current.current_workspace_fingerprint,
                changes=[
                    {
                        "path": "models/large.py",
                        "action": "modify",
                        "edits": [{"old": large, "new": replacement}],
                    }
                ],
                binding=self.binding,
            )


if __name__ == "__main__":
    unittest.main()
