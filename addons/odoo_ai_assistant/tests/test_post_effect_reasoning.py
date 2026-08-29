import asyncio
from uuid import uuid4

from odoo import SUPERUSER_ID, Command
from odoo.tests.common import TransactionCase

from ..models.embedded_runtime_host_loop import _append_verified_effect_receipt
from ..models.turn_queue import _stage_completed_turn
from ..runtime.agent import AgentTurnService, PostEffectDecisionEngine
from ..runtime.agent.contracts import FinalAnswer, PlanStepProposal
from ..runtime.agent.decision_validation import NextDecisionValidationError
from ..runtime.agent.provider_failure import (
    FailureNormalizingDecisionEngine,
    ProviderFailureError,
)
from ..runtime.agent.working_transcript import append_working_item
from ..runtime.capabilities import (
    CapabilityConfigResolver,
    CapabilityContext,
    CapabilityExecutor,
    CapabilityPolicy,
    discover_capabilities,
)


class _RepeatThenSummarizeEngine:
    def __init__(self, *, record_id):
        self.record_id = record_id
        self.calls = 0
        self.planning_catalog_sizes = []

    async def next_decision(self, *, planning_capabilities, working_items, **_kwargs):
        self.calls += 1
        self.planning_catalog_sizes.append(len(planning_capabilities))
        assert any(item.get("kind") == "verified_effect_receipt" for item in working_items)
        if self.calls == 1:
            return PlanStepProposal(
                "plan_step_proposal",
                "repeat-effect",
                "odoo.record.patch",
                {
                    "model": "res.partner",
                    "record_id": self.record_id,
                    "values": {"name": "SHOULD NEVER EXECUTE"},
                },
                "Repetir el cambio",
            )
        return FinalAnswer(
            "final_answer",
            "El cambio ya quedó aplicado y verificado.",
            "high",
        )


class _FinalOnlyEngine:
    def __init__(self):
        self.calls = 0

    async def next_decision(self, **_kwargs):
        self.calls += 1
        return FinalAnswer(
            "final_answer",
            "Resultado final desde el proveedor.",
            "high",
        )


class _FailingPostEffectProvider:
    async def next_decision(self, **_kwargs):
        raise TimeoutError("post-effect provider timeout")


class TestPostEffectReasoning(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        internal = cls.env.ref("base.group_user")
        partner_manager = cls.env.ref("base.group_partner_manager")
        system = cls.env.ref("base.group_system")
        company = cls.env.company
        cls.user = cls.env["res.users"].create(
            {
                "name": "Post Effect Reasoning User",
                "login": "post-effect-reasoning-user",
                "company_id": company.id,
                "company_ids": [Command.set([company.id])],
                "groups_id": [Command.set([internal.id, partner_manager.id, system.id])],
            }
        )

    def setUp(self):
        super().setUp()
        self.partner = self.env["res.partner"].create({"name": "POST EFFECT VERIFIED"})

    def _runtime(self):
        env = self.env(user=self.user, su=False)
        context = CapabilityContext(
            env=env,
            turn_id="post-effect-test",
            screen={"model": "res.partner", "res_id": self.partner.id},
            metadata={
                "capability_policy": {
                    "confirmation_mode": "risk_based",
                    "max_auto_risk": "moderate",
                    "max_provider_decisions": 6,
                    "max_capability_calls": 4,
                    "max_consecutive_correctable_failures": 3,
                }
            },
        )
        registry = discover_capabilities()
        executor = CapabilityExecutor(
            registry,
            context,
            policy=CapabilityPolicy(),
            config=CapabilityConfigResolver(),
        )
        return context, registry, executor

    def _verified_working_items(self):
        working = append_working_item(
            (),
            "user_input",
            {"message": "Actualiza el contacto"},
        )
        return append_working_item(
            working,
            "verified_effect_receipt",
            {
                "verified": True,
                "plan_state": "completed",
                "step_count": 1,
                "steps": [
                    {
                        "position": 0,
                        "capability": "odoo.record.patch",
                        "title": "Actualizar contacto",
                        "result": {"model": "res.partner", "record_id": self.partner.id},
                        "verification": {"name": "POST EFFECT VERIFIED"},
                    }
                ],
            },
        )

    def test_completed_approved_turn_reuses_provisional_assistant_message(self):
        env = self.env(user=self.user, su=False)
        conversation = env["odoo.ai.conversation"].create(
            {"title": "Post-effect completion"}
        )
        provisional = env["odoo.ai.message"].create(
            {
                "conversation_id": conversation.id,
                "role": "assistant",
                "content": "Propuesta pendiente de aprobación",
                "internal_workflow": "AGENT",
            }
        )
        turn = env["odoo.ai.turn"].with_user(SUPERUSER_ID).create(
            {
                "turn_uuid": str(uuid4()),
                "conversation_id": conversation.id,
                "user_id": self.user.id,
                "company_id": self.user.company_id.id,
                "state": "running",
                "input_message": "Actualiza el contacto",
                "allowed_company_ids": [self.user.company_id.id],
                "assistant_message_id": provisional.id,
            }
        )

        _stage_completed_turn(
            turn.env,
            turn,
            {"answer": "El cambio quedó aplicado y verificado."},
        )

        turn.invalidate_recordset(["assistant_message_id", "state"])
        provisional.invalidate_recordset(["content"])
        self.assertEqual(turn.state, "completed")
        self.assertEqual(turn.assistant_message_id, provisional)
        self.assertEqual(provisional.content, "El cambio quedó aplicado y verificado.")
        self.assertEqual(
            env["odoo.ai.message"].search_count(
                [
                    ("conversation_id", "=", conversation.id),
                    ("role", "=", "assistant"),
                ]
            ),
            1,
        )

    def test_verified_receipt_keeps_effect_result_and_verification(self):
        items = append_working_item((), "user_input", {"message": "Actualiza el contacto"})
        completed_plan = {
            "state": "completed",
            "steps": [
                {
                    "position": 0,
                    "capability": "odoo.record.patch",
                    "title": "Actualizar contacto",
                    "state": "completed",
                    "result": {"model": "res.partner", "record_id": self.partner.id},
                    "verification": {"name": "POST EFFECT VERIFIED"},
                }
            ],
        }

        result = _append_verified_effect_receipt(items, completed_plan)
        receipt = result[-1]
        self.assertEqual(receipt.kind, "verified_effect_receipt")
        self.assertTrue(receipt.data["verified"])
        self.assertEqual(receipt.data["plan_state"], "completed")
        self.assertEqual(receipt.data["steps"][0]["result"]["record_id"], self.partner.id)
        self.assertEqual(
            receipt.data["steps"][0]["verification"]["name"],
            "POST EFFECT VERIFIED",
        )

    def test_oversized_verified_receipt_falls_back_to_compact_authoritative_context(self):
        items = append_working_item((), "user_input", {"message": "Actualiza el contacto"})
        completed_plan = {
            "state": "completed",
            "steps": [
                {
                    "position": 0,
                    "capability": "odoo.record.patch",
                    "title": "Actualizar contacto",
                    "state": "completed",
                    "result": {
                        "model": "res.partner",
                        "record_id": self.partner.id,
                        "oversized": "x" * 40_000,
                    },
                    "verification": {"name": "POST EFFECT VERIFIED"},
                }
            ],
        }

        result = _append_verified_effect_receipt(items, completed_plan)
        receipt = result[-1]

        self.assertEqual(receipt.kind, "verified_effect_receipt")
        self.assertTrue(receipt.data["verified"])
        self.assertTrue(receipt.data["details_omitted"])
        self.assertEqual(receipt.data["step_count"], 1)
        self.assertEqual(receipt.data["capabilities"], ["odoo.record.patch"])
        self.assertNotIn("steps", receipt.data)

    def test_post_effect_boundary_requires_verified_receipt_before_provider_call(self):
        context, registry, _executor = self._runtime()
        underlying = _FinalOnlyEngine()
        engine = PostEffectDecisionEngine(underlying)
        working = append_working_item(
            (),
            "user_input",
            {"message": "Actualiza el contacto"},
        )

        with self.assertRaises(NextDecisionValidationError) as captured:
            asyncio.run(
                engine.next_decision(
                    message="Actualiza el contacto",
                    conversation_summary="",
                    context=context,
                    reasoning_capabilities=registry.for_reasoning(context),
                    planning_capabilities=registry.for_planning(context),
                    working_items=tuple(item.payload() for item in working),
                    remaining_budgets={
                        "provider_decisions": 1,
                        "capability_calls": 1,
                        "correctable_failures": 1,
                        "transcript_bytes": 1_000,
                        "result_bytes": 1_000,
                    },
                )
            )

        self.assertEqual(captured.exception.code, "agent_post_effect_receipt_missing")
        self.assertEqual(underlying.calls, 0)

    def test_post_effect_provider_failure_is_marked_after_confirmed_effect(self):
        context, registry, _executor = self._runtime()
        working = self._verified_working_items()
        engine = PostEffectDecisionEngine(
            FailureNormalizingDecisionEngine(
                _FailingPostEffectProvider(),
                component="codex",
                effect_state="confirmed",
            )
        )

        with self.assertRaises(ProviderFailureError) as captured:
            asyncio.run(
                engine.next_decision(
                    message="Actualiza el contacto",
                    conversation_summary="",
                    context=context,
                    reasoning_capabilities=registry.for_reasoning(context),
                    planning_capabilities=registry.for_planning(context),
                    working_items=tuple(item.payload() for item in working),
                    remaining_budgets={
                        "provider_decisions": 1,
                        "capability_calls": 1,
                        "correctable_failures": 1,
                        "transcript_bytes": 1_000,
                        "result_bytes": 1_000,
                    },
                )
            )

        self.assertEqual(captured.exception.failure.effect_state, "confirmed")

    def test_post_effect_boundary_rejects_repeat_plan_and_allows_natural_final_answer(self):
        context, registry, executor = self._runtime()
        working = self._verified_working_items()
        underlying = _RepeatThenSummarizeEngine(record_id=self.partner.id)
        service = AgentTurnService(
            registry=registry,
            context=context,
            executor=executor,
            decision_engine=PostEffectDecisionEngine(underlying),
            working_items=working,
            allow_plan_proposals=False,
        )

        result = asyncio.run(service.run(message="Actualiza el contacto"))

        self.partner.invalidate_recordset(["name"])
        self.assertEqual(self.partner.name, "POST EFFECT VERIFIED")
        self.assertEqual(result.plan, ())
        self.assertEqual(result.answer, "El cambio ya quedó aplicado y verificado.")
        self.assertEqual(underlying.calls, 2)
        self.assertEqual(underlying.planning_catalog_sizes, [0, 0])
        errors = [item for item in service.working_items if item.kind == "capability_error"]
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0].data["code"], "agent_plan_capability_not_allowed")
        self.assertEqual(service.working_items[-1].kind, "final_answer")
