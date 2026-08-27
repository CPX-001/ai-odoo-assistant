import json

from odoo.tests.common import TransactionCase

from ..runtime.agent.codex import _BASE_INSTRUCTIONS, _turn_input
from ..runtime.capabilities import CapabilityContext, discover_capabilities


class TestCodexPlanningContract(TransactionCase):
    def test_explicit_supported_mutation_contract_is_not_optional(self):
        instructions = " ".join(_BASE_INSTRUCTIONS.split())
        self.assertIn("Planning is an output obligation", instructions)
        self.assertIn(
            "A read-only answer with plan=[] does not satisfy an explicit supported mutation request",
            instructions,
        )
        self.assertIn("Never invent a plan capability", instructions)
        self.assertIn("approval is exclusively host policy", instructions)

    def test_patch_is_disclosed_as_bounded_plan_only_capability(self):
        env = self.env(user=self.env.ref("base.user_admin"), su=False)
        context = CapabilityContext(
            env=env,
            turn_id="codex-planning-contract",
            screen={"model": "res.partner", "selected_ids": []},
        )
        registry = discover_capabilities()
        planning = registry.for_planning(context)
        payload = json.loads(
            _turn_input(
                message="Update the selected partner phone number.",
                conversation_summary="",
                context=context,
                reasoning=registry.for_reasoning(context),
                planning=planning,
            )
        )

        descriptors = {
            item["name"]: item for item in payload["host_contract"]["planning_catalog"]
        }
        patch = descriptors["odoo.record.patch"]
        self.assertEqual(patch["meta"]["exposure"], "plan")
        self.assertEqual(patch["meta"]["risk"], "write")
        self.assertEqual(patch["meta"]["approval"], "policy")
        self.assertEqual(
            set(patch["inputSchema"]["required"]),
            {"model", "record_id", "values"},
        )
        self.assertFalse(env.su)
