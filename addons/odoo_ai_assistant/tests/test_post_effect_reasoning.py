import asyncio
from types import SimpleNamespace
from uuid import uuid4

from odoo import SUPERUSER_ID, Command
from odoo.tests.common import TransactionCase

from ..models.embedded_runtime import _browser_capability_plan, _completion_answer
from ..models.embedded_runtime_host_loop import (
    _append_verified_effect_receipt,
    _grounded_post_effect_result,
)
from ..models.turn_queue import _stage_completed_turn
from ..runtime.agent import AgentTurnService, PostEffectDecisionEngine
from ..runtime.agent.contracts import FinalAnswer, PlanStepProposal
from ..runtime.agent.decision_validation import NextDecisionValidationError
from ..runtime.agent.provider_failure import (
    FailureNormalizingDecisionEngine,
    ProviderFailureError,
)
from ..runtime.agent.service import _safe_failure_answer
from ..runtime.agent.working_transcript import (
    MAX_TRANSCRIPT_BYTES,
    WorkingTranscriptError,
    append_working_item,
    working_transcript_bytes,
)
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
        self.assertEqual(receipt.data["steps"][0]["result"], {"model": "res.partner"})

    def test_verified_receipt_reclaims_headroom_after_effect(self):
        items = append_working_item((), "user_input", {"message": "Haz el cambio"})
        items = append_working_item(
            items,
            "task_plan",
            {
                "goal": "Completar el cambio",
                "revision": 1,
                "revision_kind": "initial",
                "revision_summary": "",
                "steps": [
                    {
                        "step_id": "change",
                        "title": "Aplicar cambio",
                        "state": "in_progress",
                        "depends_on": [],
                    }
                ],
            },
        )
        for size in (8_000, 4_000, 2_000, 1_000, 500, 250, 100, 50, 10, 1):
            while True:
                try:
                    items = append_working_item(
                        items,
                        "task_plan_error",
                        {"padding": "x" * size},
                    )
                except WorkingTranscriptError as error:
                    self.assertEqual(error.code, "agent_working_transcript_too_large")
                    break
        self.assertGreater(working_transcript_bytes(items), MAX_TRANSCRIPT_BYTES - 250)

        result = _append_verified_effect_receipt(
            items,
            {
                "state": "completed",
                "steps": [
                    {
                        "position": 0,
                        "step_id": "change",
                        "capability": "odoo.record.patch",
                        "title": "Aplicar cambio",
                        "state": "completed",
                        "result": {"model": "res.partner", "record_id": self.partner.id},
                        "verification": {"name": "POST EFFECT VERIFIED"},
                    }
                ],
            },
        )

        self.assertEqual(
            [item.kind for item in result],
            ["user_input", "task_plan", "verified_effect_receipt"],
        )
        self.assertEqual(result[0].data["message"], "Haz el cambio")
        self.assertEqual(result[1].data["goal"], "Completar el cambio")
        self.assertTrue(result[2].data["verified"])

    def test_compact_verified_receipt_keeps_partial_counts_and_reason_sample(self):
        items = append_working_item((), "user_input", {"message": "Elimina contactos"})
        retained_ids = list(range(1, 121))
        result = {
            "operation": "delete",
            "model": "res.partner",
            "outcome": "partial",
            "count": 80,
            "requested_count": 200,
            "failed_count": 120,
            "excluded_count": 0,
            "failed_record_ids": retained_ids,
            "excluded_record_ids": [],
            "retained_groups": [
                {
                    "state": "failed",
                    "error_code": "record_is_referenced",
                    "message": "Another Odoo record requires these contacts.",
                    "resolution": "archive_or_remove_dependencies",
                    "blocking_model": "sale.order",
                    "record_ids": retained_ids,
                    "count": 120,
                }
            ],
            "omitted_retained_count": 0,
            "padding": "x" * 40_000,
        }
        completed_plan = {
            "state": "completed",
            "steps": [
                {
                    "position": 0,
                    "step_id": "delete-contacts",
                    "capability": "odoo.records.bulk_delete",
                    "title": "Eliminar contactos",
                    "state": "completed",
                    "result": result,
                    "verification": {
                        "operation": "delete",
                        "model": "res.partner",
                        "outcome": "partial",
                        "count": 80,
                        "requested_count": 200,
                        "failed_count": 120,
                        "excluded_count": 0,
                    },
                }
            ],
        }

        items_with_receipt = _append_verified_effect_receipt(items, completed_plan)
        receipt = items_with_receipt[-1]

        self.assertTrue(receipt.data["details_omitted"])
        compact_result = receipt.data["steps"][0]["result"]
        self.assertEqual(compact_result["outcome"], "partial")
        self.assertEqual(compact_result["count"], 80)
        self.assertEqual(compact_result["requested_count"], 200)
        self.assertEqual(compact_result["failed_count"], 120)
        self.assertEqual(len(compact_result["failed_record_ids_sample"]), 20)
        self.assertEqual(compact_result["failed_record_ids_omitted_count"], 100)
        reason = compact_result["retained_groups_sample"][0]
        self.assertEqual(reason["blocking_model"], "sale.order")
        self.assertEqual(reason["count"], 120)
        self.assertEqual(len(reason["record_ids_sample"]), 10)
        self.assertEqual(reason["record_ids_omitted_count"], 110)
        fallback = _safe_failure_answer(
            SimpleNamespace(env=SimpleNamespace(context={"lang": "es_ES"})),
            items_with_receipt,
            "agent_provider_decision_budget_exceeded",
        )
        self.assertEqual(
            fallback,
            "El resultado quedó verificado, pero la operación fue parcial: se aplicó a "
            "80 de 200 registros; 120 fallaron y 0 quedaron excluidos.",
        )

    def test_verified_receipt_keeps_dependency_skips_even_when_compacted(self):
        items = append_working_item((), "user_input", {"message": "Completa el flujo"})
        skipped = {
            "outcome": "skipped",
            "reason": "dependency_incomplete",
            "executed": False,
            "dependencies": [{"step_id": "source", "outcome": "blocked"}],
        }
        completed_plan = {
            "state": "completed",
            "steps": [
                {
                    "position": 0,
                    "step_id": "source",
                    "capability": "test.effect_source",
                    "title": "Aplicar origen",
                    "state": "completed",
                    "result": {
                        "outcome": "blocked",
                        "count": 0,
                        "requested_count": 1,
                        "failed_count": 1,
                        "excluded_count": 0,
                        "padding": "x" * 40_000,
                    },
                    "verification": {"outcome": "blocked"},
                },
                {
                    "position": 1,
                    "step_id": "dependent",
                    "capability": "test.effect_dependent",
                    "title": "Aplicar dependiente",
                    "state": "skipped",
                    "result": skipped,
                    "verification": {"verified": True, **skipped},
                },
            ],
        }

        receipt = _append_verified_effect_receipt(items, completed_plan)[-1]

        self.assertTrue(receipt.data["details_omitted"])
        self.assertEqual(receipt.data["skipped_step_count"], 1)
        self.assertEqual(receipt.data["skipped_step_ids"], ["dependent"])
        compact_skip = receipt.data["steps"][1]
        self.assertEqual(compact_skip["state"], "skipped")
        self.assertEqual(compact_skip["result"]["reason"], "dependency_incomplete")
        self.assertFalse(compact_skip["result"]["executed"])
        self.assertEqual(
            compact_skip["result"]["dependencies"],
            [{"step_id": "source", "outcome": "blocked"}],
        )

    def test_partial_business_outcome_is_projected_without_rewriting_effect_plan(self):
        internal_plan = {
            "state": "completed",
            "requires_confirmation": True,
            "steps": [
                {
                    "position": 0,
                    "capability": "odoo.records.bulk_delete",
                    "title": "Eliminar contactos",
                    "state": "completed",
                    "risk": "protected",
                    "effect": "internal_irreversible",
                    "approval": "always",
                    "preview": {"operation": "delete", "count": 3},
                    "result": {
                        "operation": "delete",
                        "model": "res.partner",
                        "outcome": "blocked",
                        "count": 0,
                        "requested_count": 3,
                        "failed_count": 3,
                        "excluded_count": 0,
                    },
                    "verification": {"outcome": "blocked", "count": 0},
                },
                {
                    "position": 1,
                    "capability": "test.effect_dependent",
                    "title": "Aplicar paso dependiente",
                    "state": "skipped",
                    "risk": "moderate",
                    "effect": "internal_reversible",
                    "approval": "policy",
                    "preview": {"operation": "synthetic", "count": 1},
                    "result": {
                        "outcome": "skipped",
                        "reason": "dependency_incomplete",
                        "executed": False,
                        "dependencies": [
                            {"step_id": "delete-source", "outcome": "blocked"}
                        ],
                    },
                    "verification": {
                        "verified": True,
                        "outcome": "skipped",
                        "reason": "dependency_incomplete",
                        "executed": False,
                        "dependencies": [
                            {"step_id": "delete-source", "outcome": "blocked"}
                        ],
                    },
                },
                {
                    "position": 2,
                    "step_id": "independent",
                    "capability": "test.effect_independent",
                    "title": "Aplicar paso independiente",
                    "state": "completed",
                    "risk": "moderate",
                    "effect": "internal_reversible",
                    "approval": "policy",
                    "preview": {"operation": "synthetic", "count": 1},
                    "result": {
                        "outcome": "completed",
                        "count": 1,
                        "requested_count": 1,
                        "failed_count": 0,
                        "excluded_count": 0,
                    },
                    "verification": {"verified": True},
                },
            ],
        }

        browser_plan = _browser_capability_plan(
            SimpleNamespace(
                turn_uuid="partial-business-outcome-test",
                input_message="Elimina los contactos",
            ),
            internal_plan,
            {
                "confirmation_mode": "always_confirm",
                "max_auto_risk": "low",
                "allow_synthetic_data": False,
            },
        )

        self.assertEqual(internal_plan["state"], "completed")
        self.assertEqual(internal_plan["steps"][0]["state"], "completed")
        self.assertEqual(browser_plan["state"], "partial")
        self.assertEqual(browser_plan["steps"][0]["state"], "partial")
        self.assertEqual(browser_plan["steps"][0]["receipt"]["outcome"], "blocked")
        self.assertEqual(browser_plan["steps"][1]["state"], "skipped")
        self.assertEqual(browser_plan["steps"][1]["receipt"]["outcome"], "skipped")
        self.assertEqual(
            browser_plan["steps"][1]["receipt"]["error_code"],
            "dependency_incomplete",
        )
        self.assertEqual(
            _completion_answer(internal_plan),
            "El resultado quedó verificado: no se pudo aplicar la operación a ninguno de "
            "los 3 registros; 3 fallaron y 0 quedaron excluidos.",
        )

    def test_malformed_outcome_field_does_not_change_completion_semantics(self):
        internal_plan = {
            "state": "completed",
            "requires_confirmation": False,
            "steps": [
                {
                    "position": 0,
                    "capability": "test.arbitrary_result",
                    "title": "Completar acción",
                    "state": "completed",
                    "risk": "low",
                    "effect": "none",
                    "approval": "never",
                    "preview": {"operation": "inspect", "count": 1},
                    "result": {"outcome": "partial", "note": "domain value"},
                    "verification": {"verified": True},
                }
            ],
        }

        browser_plan = _browser_capability_plan(
            SimpleNamespace(
                turn_uuid="arbitrary-outcome-test",
                input_message="Inspecciona el registro",
            ),
            internal_plan,
            {
                "confirmation_mode": "risk_based",
                "max_auto_risk": "moderate",
                "allow_synthetic_data": False,
            },
        )

        self.assertEqual(browser_plan["state"], "completed")
        self.assertEqual(browser_plan["steps"][0]["state"], "completed")
        self.assertEqual(browser_plan["steps"][0]["receipt"]["outcome"], "verified")
        self.assertEqual(
            _completion_answer(internal_plan),
            "He completado y verificado la acción: Completar acción",
        )

    def test_incomplete_receipt_overrides_contradictory_provider_summary(self):
        answer, confidence = _grounded_post_effect_result(
            {
                "state": "completed",
                "steps": [
                    {
                        "state": "completed",
                        "result": {
                            "outcome": "partial",
                            "count": 7,
                            "requested_count": 10,
                            "failed_count": 3,
                            "excluded_count": 0,
                        },
                    }
                ],
            },
            provider_answer="Todo se completó correctamente: 10 de 10.",
            provider_confidence="high",
            lang="es_ES",
        )

        self.assertEqual(confidence, "high")
        self.assertNotIn("10 de 10", answer)
        self.assertEqual(
            answer,
            "El resultado quedó verificado, pero la operación fue parcial: se aplicó a "
            "7 de 10 registros; 3 fallaron y 0 quedaron excluidos.",
        )

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

    def test_confirmed_provider_failure_can_finish_from_verified_receipt(self):
        context, registry, executor = self._runtime()
        service = AgentTurnService(
            registry=registry,
            context=context,
            executor=executor,
            decision_engine=PostEffectDecisionEngine(
                FailureNormalizingDecisionEngine(
                    _FailingPostEffectProvider(),
                    component="codex",
                    effect_state="confirmed",
                )
            ),
            working_items=self._verified_working_items(),
            allow_plan_proposals=False,
        )

        with self.assertRaises(ProviderFailureError) as captured:
            asyncio.run(service.run(message="Actualiza el contacto"))
        result = asyncio.run(service.finish_safely(captured.exception.code))

        self.assertEqual(result.plan, ())
        self.assertIn("quedó verificado en Odoo", result.answer)
        self.assertNotIn("error", result.answer.lower())
        self.assertEqual(service.working_items[-1].kind, "final_answer")
        self.assertEqual(
            service.working_items[-1].data["host_fallback_code"],
            captured.exception.code,
        )

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
