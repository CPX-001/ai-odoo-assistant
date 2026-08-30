"""Dependency-light checks for Phase 6 recovery units and EffectJournal boundaries."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PLAN = ROOT / "addons" / "odoo_ai_assistant" / "runtime" / "agent" / "plan.py"
RECOVERY = ROOT / "addons" / "odoo_ai_assistant" / "models" / "effect_recovery_runtime.py"
JOURNAL = ROOT / "addons" / "odoo_ai_assistant" / "models" / "effect_journal.py"
ACCESS = ROOT / "addons" / "odoo_ai_assistant" / "security" / "ir.model.access.csv"


class TestPhase6EffectRecoveryContract(unittest.TestCase):
    def test_effect_plan_v3_models_host_owned_recovery_units(self):
        source = PLAN.read_text(encoding="utf-8")

        self.assertIn('"format_version": 3', source)
        self.assertIn('"recovery_units": recovery_units', source)
        self.assertIn('"recovery_unit_id"', source)
        self.assertIn('"recovery_mode"', source)
        self.assertIn('"journal_classification"', source)
        self.assertIn('"odoo_atomic"', source)
        self.assertIn('"segmented"', source)
        self.assertIn('"external"', source)
        self.assertNotIn("Codex", source)

    def test_inflight_recovery_unit_is_never_blindly_replayed(self):
        source = PLAN.read_text(encoding="utf-8")

        self.assertIn('unit["state"] == "executing"', source)
        self.assertIn('"capability_plan_recovery_required"', source)
        self.assertIn('"capability_plan_recovery_checkpoint_required"', source)
        self.assertIn('verification.verified is not True', source)

    def test_host_checkpoints_each_unit_and_reacquires_effect_lock(self):
        source = RECOVERY.read_text(encoding="utf-8")

        self.assertIn('phase not in {"before_unit", "after_unit"}', source)
        self.assertIn("acquire_turn_effect_lock(turn.env.cr, turn.turn_uuid)", source)
        self.assertIn("_ensure_turn_control_current(turn)", source)
        self.assertIn("_commit_plan_barrier(", source)
        self.assertGreaterEqual(source.count("technical.env.cr.commit()"), 2)
        self.assertIn("recovery_checkpoint=recovery_checkpoint", source)

    def test_effect_journal_is_short_lived_bounded_and_browser_sanitized(self):
        source = JOURNAL.read_text(encoding="utf-8")

        self.assertIn("_RETENTION_DAYS = 7", source)
        self.assertIn("_MAX_PAYLOAD_BYTES = 64 * 1024", source)
        for classification in (
            "reversible",
            "reconstructable",
            "irreversible",
            "external_or_unknown",
        ):
            self.assertIn(f'"{classification}"', source)
        browser = source[source.index("def _browser_row(row):") :]
        self.assertNotIn('"before_payload"', browser)
        self.assertNotIn('"after_payload"', browser)
        self.assertNotIn('"receipt_payload"', browser)
        self.assertIn('"reconstructable": row.classification == "reconstructable"', browser)

    def test_effect_journal_table_is_not_directly_exposed_to_normal_users(self):
        rows = ACCESS.read_text(encoding="utf-8").splitlines()
        journal_rows = [row for row in rows if "effect_journal" in row]

        self.assertEqual(len(journal_rows), 1)
        self.assertIn("base.group_system", journal_rows[0])
        self.assertNotIn("base.group_user", journal_rows[0])


if __name__ == "__main__":
    unittest.main()
