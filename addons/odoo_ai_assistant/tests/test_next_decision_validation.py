from odoo.tests.common import TransactionCase

from ..runtime.agent.contracts import PlanStepProposal, ReasoningCapabilityCall
from ..runtime.agent.decision_validation import (
    NextDecisionValidationError,
    validate_next_decision,
)
from ..runtime.capabilities import CapabilityContext, discover_capabilities


class TestNextDecisionValidation(TransactionCase):
    def _catalogs(self):
        env = self.env(user=self.env.ref("base.user_admin"), su=False)
        context = CapabilityContext(
            env=env,
            turn_id="next-decision-validation",
            screen={"model": "res.partner", "selected_ids": []},
            metadata={"capability_policy": {}},
        )
        registry = discover_capabilities()
        return registry.for_reasoning(context), registry.for_planning(context)

    def test_unknown_or_wrong_exposure_is_rejected_before_execution(self):
        reasoning, planning = self._catalogs()
        with self.assertRaisesRegex(
            NextDecisionValidationError, "agent_reasoning_capability_not_allowed"
        ):
            validate_next_decision(
                ReasoningCapabilityCall(
                    kind="reasoning_capability_call",
                    call_id="call-1",
                    capability="odoo.record.patch",
                    arguments={"model": "res.partner", "record_id": 1, "values": {"name": "X"}},
                ),
                reasoning_capabilities=reasoning,
                planning_capabilities=planning,
            )

    def test_schema_invalid_reasoning_arguments_fail_closed(self):
        reasoning, planning = self._catalogs()
        with self.assertRaisesRegex(
            NextDecisionValidationError, "agent_capability_arguments_invalid"
        ):
            validate_next_decision(
                ReasoningCapabilityCall(
                    kind="reasoning_capability_call",
                    call_id="call-2",
                    capability="odoo.get_effective_schema",
                    arguments={},
                ),
                reasoning_capabilities=reasoning,
                planning_capabilities=planning,
            )

    def test_plan_proposal_is_validated_but_never_executed(self):
        reasoning, planning = self._catalogs()
        proposal = validate_next_decision(
            PlanStepProposal(
                kind="plan_step_proposal",
                call_id="call-3",
                capability="odoo.record.patch",
                arguments={"model": "res.partner", "record_id": 1, "values": {"name": "X"}},
                user_summary="  Actualizar   contacto  ",
            ),
            reasoning_capabilities=reasoning,
            planning_capabilities=planning,
        )
        self.assertEqual(proposal.capability, "odoo.record.patch")
        self.assertEqual(proposal.user_summary, "Actualizar contacto")
