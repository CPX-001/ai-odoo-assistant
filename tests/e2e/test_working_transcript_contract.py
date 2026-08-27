"""Dependency-light E2E-2 tests for the durable working transcript contract."""

from __future__ import annotations

import importlib.util
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
MODULE = ROOT / "addons/odoo_ai_assistant/runtime/agent/working_transcript.py"
spec = importlib.util.spec_from_file_location("e2e_working_transcript", MODULE)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


class TestWorkingTranscriptContract(unittest.TestCase):
    def test_roundtrip_preserves_pending_and_completed_call_state(self):
        items = ()
        items = module.append_working_item(items, "user_input", {"message": "hi"})
        items = module.append_working_item(
            items,
            "assistant_decision",
            {
                "call_id": "c1",
                "decision_kind": "reasoning_capability_call",
                "capability": "odoo.test.read",
                "arguments": {},
            },
        )
        items = module.append_working_item(
            items,
            "capability_call",
            {"call_id": "c1", "capability": "odoo.test.read", "arguments": {}},
        )
        self.assertEqual(module.call_state(items, "c1"), "pending")
        items = module.append_working_item(
            items,
            "capability_result",
            {"call_id": "c1", "capability": "odoo.test.read", "result": {"ok": True}},
        )
        self.assertEqual(module.call_state(items, "c1"), "completed")
        self.assertEqual(module.load_working_transcript(module.transcript_payload(items)), items)

    def test_sequence_duplicate_terminal_and_call_id_reuse_fail_closed(self):
        with self.assertRaises(module.WorkingTranscriptError):
            module.load_working_transcript(
                [{"sequence": 2, "kind": "user_input", "data": {}}]
            )
        duplicate_terminal = (
            module.WorkingItem(1, "capability_result", {"call_id": "c", "result": {}}),
            module.WorkingItem(2, "capability_error", {"call_id": "c", "code": "x"}),
        )
        with self.assertRaisesRegex(module.WorkingTranscriptError, "terminal_duplicate"):
            module.transcript_payload(duplicate_terminal)
        items = module.append_working_item(
            (),
            "assistant_decision",
            {
                "call_id": "c",
                "decision_kind": "reasoning_capability_call",
                "capability": "odoo.a",
                "arguments": {},
            },
        )
        with self.assertRaisesRegex(module.WorkingTranscriptError, "call_id_duplicate"):
            module.append_working_item(
                items,
                "assistant_decision",
                {
                    "call_id": "c",
                    "decision_kind": "reasoning_capability_call",
                    "capability": "odoo.a",
                    "arguments": {},
                },
            )

    def test_result_and_total_bounds_fail_closed(self):
        with self.assertRaisesRegex(module.WorkingTranscriptError, "too_large"):
            module.append_working_item(
                (),
                "capability_result",
                {"call_id": "c", "result": "x" * (module.MAX_RESULT_BYTES + 1)},
            )

    def test_private_transcript_is_not_a_public_event_contract(self):
        self.assertNotIn("public", module._ALLOWED_KINDS)
        self.assertNotIn("diagnostic", module._ALLOWED_KINDS)


if __name__ == "__main__":
    unittest.main()
