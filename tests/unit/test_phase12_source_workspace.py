from __future__ import annotations

import shutil
import stat
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "addons" / "odoo_ai_assistant" / "runtime"))

from source_workspace import SourceWorkspaceError, SourceWorkspaceStore


class SourceWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / "installed" / "fixture_addon"
        self.workspace_root = self.root / "runtime" / "workspaces"
        (self.source / "models").mkdir(parents=True)
        (self.source / "views").mkdir()
        (self.source / "models" / "sale.py").write_text(
            "class SaleOrder:\n    pass\n"
        )
        (self.source / "views" / "sale.xml").write_text("<odoo/>\n")
        (self.source / "__manifest__.py").write_text("{'name': 'Fixture'}\n")
        (self.source / ".env").write_text("SECRET=not-copied\n")
        self.store = SourceWorkspaceStore(self.workspace_root).ensure()
        self.binding = {
            "odoo_uid": 7,
            "company_id": 3,
            "database_fingerprint": "sha256:" + "d" * 64,
            "turn_id": "turn-test-0001",
        }

    def tearDown(self):
        self.temp.cleanup()

    def test_prepare_is_path_free_and_does_not_mutate_source(self):
        before = {
            path.relative_to(self.source).as_posix(): path.read_bytes()
            for path in self.source.rglob("*")
            if path.is_file()
        }
        receipt = self.store.prepare(
            module="fixture_addon",
            source_root=self.source,
            binding=self.binding,
        )
        public = receipt.public_metadata()

        self.assertEqual(public["module"], "fixture_addon")
        self.assertEqual(public["source_id"], "odoo-addon:fixture_addon")
        self.assertEqual(
            public["source_fingerprint"],
            public["baseline_workspace_fingerprint"],
        )
        self.assertFalse(public["workspace_changed"])
        self.assertFalse(public["source_stale"])
        self.assertNotIn(str(self.source), repr(public))
        self.assertNotIn(str(self.workspace_root), repr(public))
        self.assertFalse((receipt.workspace_path / ".env").exists())
        self.assertTrue((receipt.workspace_path / "models" / "sale.py").is_file())
        self.assertEqual(
            stat.S_IMODE(receipt.workspace_path.stat().st_mode),
            0o700,
        )
        self.assertEqual(
            stat.S_IMODE((receipt.workspace_path / "models" / "sale.py").stat().st_mode),
            0o600,
        )
        self.assertEqual(
            stat.S_IMODE(
                (receipt.workspace_path / ".odoo-ai-workspace.json").stat().st_mode
            ),
            0o600,
        )

        self.store.inspect(
            receipt.workspace_id,
            source_root=self.source,
            binding=self.binding,
        )
        self.store.delete(receipt.workspace_id, binding=self.binding)
        after = {
            path.relative_to(self.source).as_posix(): path.read_bytes()
            for path in self.source.rglob("*")
            if path.is_file()
        }
        self.assertEqual(after, before)

    def test_workspace_change_and_source_staleness_are_independent(self):
        receipt = self.store.prepare(
            module="fixture_addon",
            source_root=self.source,
            binding=self.binding,
        )
        staged = receipt.workspace_path / "models" / "sale.py"
        staged.write_text("class SaleOrder:\n    changed = True\n")
        changed = self.store.inspect(
            receipt.workspace_id,
            source_root=self.source,
            binding=self.binding,
        )
        self.assertTrue(changed.workspace_changed)
        self.assertFalse(changed.source_stale)
        self.assertNotEqual(
            changed.current_workspace_fingerprint,
            changed.source_fingerprint,
        )

        (self.source / "views" / "sale.xml").write_text(
            "<odoo><record/></odoo>\n"
        )
        stale = self.store.inspect(
            receipt.workspace_id,
            source_root=self.source,
            binding=self.binding,
        )
        self.assertTrue(stale.workspace_changed)
        self.assertTrue(stale.source_stale)

    def test_host_generates_distinct_workspace_ids_for_same_source(self):
        first = self.store.prepare(
            module="fixture_addon",
            source_root=self.source,
            binding=self.binding,
        )
        second = self.store.prepare(
            module="fixture_addon",
            source_root=self.source,
            binding=self.binding,
        )
        self.assertNotEqual(first.workspace_id, second.workspace_id)
        self.assertEqual(first.source_fingerprint, second.source_fingerprint)

        mirror = self.root / "different-physical-root" / "fixture_addon"
        shutil.copytree(self.source, mirror)
        for path in mirror.rglob("*"):
            if path.is_file():
                path.touch()
        mirrored = self.store.prepare(
            module="fixture_addon",
            source_root=mirror,
            binding=self.binding,
        )
        self.assertEqual(first.source_fingerprint, mirrored.source_fingerprint)

    def test_symlink_source_entry_fails_closed(self):
        outside = self.root / "outside.py"
        outside.write_text("secret = True\n")
        (self.source / "models" / "escape.py").symlink_to(outside)
        with self.assertRaisesRegex(
            SourceWorkspaceError,
            "source_workspace_source_symlink",
        ):
            self.store.prepare(
                module="fixture_addon",
                source_root=self.source,
                binding=self.binding,
            )

        linked_root = self.root / "linked-source-root"
        linked_root.symlink_to(self.source, target_is_directory=True)
        with self.assertRaisesRegex(
            SourceWorkspaceError,
            "source_workspace_source_symlink",
        ):
            self.store.prepare(
                module="fixture_addon",
                source_root=linked_root,
                binding=self.binding,
            )

    def test_source_and_workspace_roots_must_be_disjoint(self):
        nested = SourceWorkspaceStore(self.source / "workspace").ensure()
        with self.assertRaisesRegex(
            SourceWorkspaceError,
            "source_workspace_root_overlap",
        ):
            nested.prepare(
                module="fixture_addon",
                source_root=self.source,
                binding=self.binding,
            )

    def test_invalid_module_and_workspace_ids_are_rejected(self):
        with self.assertRaisesRegex(
            SourceWorkspaceError,
            "source_workspace_module_invalid",
        ):
            self.store.prepare(
                module="../fixture",
                source_root=self.source,
                binding=self.binding,
            )
        with self.assertRaisesRegex(
            SourceWorkspaceError,
            "source_workspace_id_invalid",
        ):
            self.store.inspect("../../etc/passwd", binding=self.binding)

    def test_bounds_are_enforced_before_publish(self):
        cases = (
            (
                SourceWorkspaceStore(
                    self.root / "too-many",
                    max_files=2,
                    max_total_bytes=1024,
                    max_file_bytes=1024,
                ).ensure(),
                "source_workspace_too_many_files",
            ),
            (
                SourceWorkspaceStore(
                    self.root / "file-too-large",
                    max_files=10,
                    max_total_bytes=1024,
                    max_file_bytes=8,
                ).ensure(),
                "source_workspace_file_too_large",
            ),
            (
                SourceWorkspaceStore(
                    self.root / "total-too-large",
                    max_files=10,
                    max_total_bytes=40,
                    max_file_bytes=32,
                ).ensure(),
                "source_workspace_total_too_large",
            ),
        )
        for store, error_code in cases:
            with self.subTest(error_code=error_code):
                with self.assertRaisesRegex(SourceWorkspaceError, error_code):
                    store.prepare(
                        module="fixture_addon",
                        source_root=self.source,
                        binding=self.binding,
                    )
                self.assertEqual(list(store.workspace_root.iterdir()), [])

    def test_secret_named_workspace_tamper_is_not_hidden(self):
        receipt = self.store.prepare(
            module="fixture_addon",
            source_root=self.source,
            binding=self.binding,
        )
        (receipt.workspace_path / ".env").write_text("MALICIOUS=1\n")
        with self.assertRaisesRegex(
            SourceWorkspaceError,
            "source_workspace_secret_entry",
        ):
            self.store.inspect(receipt.workspace_id, binding=self.binding)

    def test_workspace_binding_is_not_transferable(self):
        receipt = self.store.prepare(
            module="fixture_addon",
            source_root=self.source,
            binding=self.binding,
        )
        changed_bindings = (
            dict(self.binding, odoo_uid=8),
            dict(self.binding, company_id=4),
            dict(self.binding, database_fingerprint="sha256:" + "e" * 64),
            dict(self.binding, turn_id="turn-test-0002"),
        )
        for other in changed_bindings:
            with self.subTest(binding=other), self.assertRaisesRegex(
                SourceWorkspaceError,
                "source_workspace_binding_mismatch",
            ):
                self.store.inspect(receipt.workspace_id, binding=other)

    def test_delete_cannot_escape_managed_root(self):
        receipt = self.store.prepare(
            module="fixture_addon",
            source_root=self.source,
            binding=self.binding,
        )
        self.store.delete(receipt.workspace_id, binding=self.binding)
        self.assertFalse(receipt.workspace_path.exists())
        with self.assertRaisesRegex(
            SourceWorkspaceError,
            "source_workspace_id_invalid",
        ):
            self.store.delete("workspace:v1:../outside", binding=self.binding)


if __name__ == "__main__":
    unittest.main()
