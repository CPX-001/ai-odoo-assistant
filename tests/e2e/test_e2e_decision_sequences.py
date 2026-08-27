"""Static contract checks for the E2E-0 decision-sequence eval catalog.

This file intentionally uses only the Python standard library so the fixture gate can run even
outside an Odoo checkout/runtime. Product behavior is exercised by addon tests in later slices.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

_FIXTURE = Path(__file__).with_name("e2e_decision_sequences.json")
_ALLOWED_KINDS = {
    "final_answer",
    "reasoning_capability_call",
    "plan_step_proposal",
}
_REQUIRED_CASES = {
    "hello",
    "read_partner",
    "multi_read_synthesis",
    "supported_patch",
    "supported_create",
    "validation_repair",
    "access_denied",
    "unsupported_action",
}


class TestE2EDecisionSequences(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload = json.loads(_FIXTURE.read_text(encoding="utf-8"))

    def test_catalog_is_complete_and_every_case_is_bounded(self):
        self.assertEqual(self.payload["format_version"], 1)
        defaults = self.payload["defaults"]
        self.assertEqual(
            set(defaults),
            {
                "max_provider_decisions",
                "max_capability_calls",
                "max_consecutive_correctable_failures",
                "max_transcript_bytes",
                "max_result_bytes",
            },
        )
        self.assertGreater(defaults["max_provider_decisions"], 0)
        self.assertGreater(defaults["max_capability_calls"], 0)
        self.assertGreater(defaults["max_consecutive_correctable_failures"], 0)
        self.assertGreater(defaults["max_transcript_bytes"], defaults["max_result_bytes"])

        cases = {case["id"]: case for case in self.payload["cases"]}
        self.assertEqual(set(cases), _REQUIRED_CASES)
        for case in cases.values():
            decisions = case["expected_decisions"]
            self.assertGreaterEqual(len(decisions), 1)
            self.assertLessEqual(len(decisions), case["max_provider_decisions"])
            self.assertLessEqual(case["max_provider_decisions"], defaults["max_provider_decisions"])
            calls = sum(item["kind"] == "reasoning_capability_call" for item in decisions)
            self.assertLessEqual(calls, case["max_capability_calls"])
            self.assertLessEqual(case["max_capability_calls"], defaults["max_capability_calls"])
            self.assertTrue(all(item["kind"] in _ALLOWED_KINDS for item in decisions))

    def test_supported_mutations_terminate_in_one_canonical_plan_proposal(self):
        by_id = {case["id"]: case for case in self.payload["cases"]}
        for case_id, capability in (
            ("supported_patch", "odoo.record.patch"),
            ("supported_create", "odoo.record.create"),
        ):
            decisions = by_id[case_id]["expected_decisions"]
            proposals = [item for item in decisions if item["kind"] == "plan_step_proposal"]
            self.assertEqual(proposals, [{"kind": "plan_step_proposal", "capability": capability}])
            self.assertEqual(decisions[-1], proposals[0])

    def test_read_paths_end_in_final_answer_and_never_plan(self):
        by_id = {case["id"]: case for case in self.payload["cases"]}
        for case_id in ("hello", "read_partner", "multi_read_synthesis", "unsupported_action"):
            decisions = by_id[case_id]["expected_decisions"]
            self.assertEqual(decisions[-1]["kind"], "final_answer")
            self.assertFalse(any(item["kind"] == "plan_step_proposal" for item in decisions))

    def test_repair_and_denial_are_explicit_host_observations(self):
        by_id = {case["id"]: case for case in self.payload["cases"]}
        repair = by_id["validation_repair"]["expected_decisions"]
        self.assertEqual(repair[0]["host_result"], "agent_capability_arguments_invalid")
        self.assertEqual(repair[-1]["kind"], "final_answer")
        denied = by_id["access_denied"]["expected_decisions"]
        self.assertEqual(denied[0]["host_result"], "access_denied")
        self.assertEqual(denied[-1]["kind"], "final_answer")


if __name__ == "__main__":
    unittest.main()
