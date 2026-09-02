import asyncio

from odoo import Command
from odoo.tests.common import TransactionCase

from ..runtime.agent import (
    CapabilityPlanError,
    CapabilityPlanService,
    CapabilityPlanStepError,
    PlannedCapability,
)
from ..runtime.capabilities import (
    CapabilityConfigResolver,
    CapabilityContext,
    CapabilityExecutor,
    CapabilityPolicy,
    clear_discovery_cache,
    discover_capabilities,
)
from ..runtime.capabilities.contracts import CapabilityError


def _policy(mode, risk):
    return {
        "confirmation_mode": mode,
        "max_auto_risk": risk,
        "allow_synthetic_data": False,
        "synthetic_data_authorized": False,
        "max_tool_calls_per_turn": 32,
        "max_write_steps_per_plan": 12,
        "max_replans": 2,
        "max_consecutive_failures": 3,
    }


class TestCapabilityActionPolicyRevalidation(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        system_group = cls.env.ref("base.group_system")
        internal_group = cls.env.ref("base.group_user")
        partner_manager_group = cls.env.ref("base.group_partner_manager")
        company = cls.env.company
        cls.action_user = cls.env["res.users"].create(
            {
                "name": "AI Policy Revalidation User",
                "login": "ai-policy-revalidation-user",
                "company_id": company.id,
                "company_ids": [Command.set([company.id])],
                "groups_id": [
                    Command.set(
                        [internal_group.id, partner_manager_group.id, system_group.id]
                    )
                ],
            }
        )

    def setUp(self):
        super().setUp()
        clear_discovery_cache()
        self.target = self.env["res.partner"].create({"name": "AI POLICY ORIGINAL"})

    def _plan_service(self, policy):
        env = self.env(user=self.action_user, su=False)
        context = CapabilityContext(
            env=env,
            turn_id="policy-revalidation-test",
            screen={"model": "res.partner", "res_id": self.target.id},
            metadata={"capability_policy": policy},
        )
        registry = discover_capabilities()
        executor = CapabilityExecutor(
            registry,
            context,
            policy=CapabilityPolicy(),
            config=CapabilityConfigResolver(),
        )
        return CapabilityPlanService(registry=registry, executor=executor)

    def _patch(self):
        return (
            PlannedCapability(
                capability="odoo.record.patch",
                arguments={
                    "model": "res.partner",
                    "record_id": self.target.id,
                    "values": {"name": "AI POLICY UPDATED"},
                },
                summary="Cambiar el nombre del contacto",
            ),
        )

    def test_policy_tightening_requires_real_approval_before_barrier(self):
        permissive = self._plan_service(_policy("protected_only", "protected"))
        prepared = asyncio.run(permissive.prepare(self._patch()))
        self.assertEqual(prepared["state"], "authorized")
        self.assertFalse(prepared["requires_confirmation"])

        strict = self._plan_service(_policy("always_confirm", "low"))
        barrier_calls = []
        with self.assertRaises(CapabilityPlanError) as captured:
            asyncio.run(
                strict.execute(
                    prepared,
                    human_approved=False,
                    before_effect=lambda: barrier_calls.append("crossed"),
                )
            )

        self.assertEqual(captured.exception.code, "capability_plan_approval_required")
        self.assertEqual(barrier_calls, [])
        self.target.invalidate_recordset(["name"])
        self.assertEqual(self.target.name, "AI POLICY ORIGINAL")

    def test_policy_tightening_accepts_explicit_human_approval(self):
        permissive = self._plan_service(_policy("protected_only", "protected"))
        prepared = asyncio.run(permissive.prepare(self._patch()))

        strict = self._plan_service(_policy("always_confirm", "low"))
        barrier_calls = []
        executed = asyncio.run(
            strict.execute(
                prepared,
                human_approved=True,
                before_effect=lambda: barrier_calls.append("crossed"),
            )
        )

        self.assertEqual(barrier_calls, ["crossed"])
        self.assertEqual(executed.payload["state"], "completed")
        self.target.invalidate_recordset(["name"])
        self.assertEqual(self.target.name, "AI POLICY UPDATED")

    def test_execution_failure_is_bound_to_the_failed_step_for_agent_repair(self):
        plans = self._plan_service(_policy("always_confirm", "low"))
        prepared = asyncio.run(plans.prepare(self._patch()))
        authorized = dict(prepared)
        authorized["state"] = "authorized"

        async def reject_execution(*_args, **_kwargs):
            raise CapabilityError(
                "action_rejected",
                details={"model": "res.partner", "operation": "patch"},
            )

        plans._executor.execute = reject_execution

        with self.assertRaises(CapabilityPlanStepError) as captured:
            asyncio.run(plans.execute(authorized, human_approved=True))

        self.assertEqual(captured.exception.code, "action_rejected")
        self.assertEqual(captured.exception.step_id, prepared["steps"][0]["step_id"])
        self.assertEqual(captured.exception.capability, "odoo.record.patch")
        self.assertEqual(captured.exception.phase, "execution")
        self.assertEqual(
            captured.exception.details,
            {"model": "res.partner", "operation": "patch"},
        )

    def test_preflight_failure_is_bound_without_claiming_a_rollback(self):
        plans = self._plan_service(_policy("always_confirm", "low"))
        prepared = asyncio.run(plans.prepare(self._patch()))
        authorized = dict(prepared)
        authorized["state"] = "authorized"
        self.target.unlink()

        with self.assertRaises(CapabilityPlanStepError) as captured:
            asyncio.run(plans.execute(authorized, human_approved=True))

        self.assertEqual(captured.exception.code, "record_not_found")
        self.assertEqual(captured.exception.phase, "preflight")
        self.assertEqual(captured.exception.details, {})
