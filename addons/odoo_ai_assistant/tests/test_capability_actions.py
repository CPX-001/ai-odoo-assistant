import asyncio

from odoo import Command, SUPERUSER_ID
from odoo.tests.common import TransactionCase

from ..models.chat_policy import resolve_capability_policy
from ..runtime.agent import (
    AgentReasoningResult,
    AgentTurnService,
    CapabilityPlanError,
    CapabilityPlanService,
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


class _PatchReasoningEngine:
    def __init__(self, record_id):
        self.record_id = record_id

    async def run_agent_turn(
        self,
        *,
        message,
        conversation_summary,
        context,
        reasoning_capabilities,
        planning_capabilities,
        executor,
    ):
        del message, conversation_summary, context, reasoning_capabilities, executor
        names = {item.name for item in planning_capabilities}
        assert "odoo.record.patch" in names
        return AgentReasoningResult(
            answer="He preparado el cambio solicitado.",
            confidence="high",
            plan=(
                PlannedCapability(
                    capability="odoo.record.patch",
                    arguments={
                        "model": "res.partner",
                        "record_id": self.record_id,
                        "values": {"name": "AI ACTION UPDATED"},
                    },
                    summary="Cambiar el nombre del contacto",
                ),
            ),
        )


class TestCapabilityActions(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        system_group = cls.env.ref("base.group_system")
        company = cls.env.company
        cls.action_user = cls.env["res.users"].create(
            {
                "name": "AI Action User",
                "login": "ai-action-user",
                "company_id": company.id,
                "company_ids": [Command.set([company.id])],
                "groups_id": [Command.set([system_group.id])],
            }
        )

    def setUp(self):
        super().setUp()
        clear_discovery_cache()
        self.target = self.env["res.partner"].create({"name": "AI ACTION ORIGINAL"})

    def _context(self, *, events=None):
        env = self.env(user=self.action_user, su=False)
        sink = None
        if events is not None:
            sink = lambda event_type, title, payload: events.append(
                (event_type, title, dict(payload))
            )
        return CapabilityContext(
            env=env,
            turn_id="action-lifecycle-test",
            screen={"model": "res.partner", "res_id": self.target.id},
            event_sink=sink,
            metadata={
                "capability_policy": {
                    "confirmation_mode": "always_confirm",
                    "max_auto_risk": "low",
                    "allow_synthetic_data": False,
                    "synthetic_data_authorized": False,
                    "max_tool_calls_per_turn": 32,
                    "max_write_steps_per_plan": 12,
                    "max_replans": 2,
                    "max_consecutive_failures": 3,
                }
            },
        )

    def _runtime(self, *, events=None):
        context = self._context(events=events)
        registry = discover_capabilities()
        executor = CapabilityExecutor(
            registry,
            context,
            policy=CapabilityPolicy(),
            config=CapabilityConfigResolver(),
        )
        plans = CapabilityPlanService(registry=registry, executor=executor)
        return context, registry, executor, plans

    def _planned_patch(self):
        return (
            PlannedCapability(
                capability="odoo.record.patch",
                arguments={
                    "model": "res.partner",
                    "record_id": self.target.id,
                    "values": {"name": "AI ACTION UPDATED"},
                },
                summary="Cambiar el nombre del contacto",
            ),
        )

    def test_agent_plan_preview_approve_execute_and_verify_under_real_user(self):
        events = []
        context, registry, executor, plans = self._runtime(events=events)
        service = AgentTurnService(
            registry=registry,
            context=context,
            executor=executor,
            reasoning_engine=_PatchReasoningEngine(self.target.id),
        )
        result = asyncio.run(service.run(message="Cambia el nombre del contacto"))
        prepared = asyncio.run(plans.prepare(result.plan))

        self.assertFalse(context.env.su)
        self.assertEqual(prepared["state"], "awaiting_confirmation")
        self.assertTrue(prepared["requires_confirmation"])
        self.assertEqual(prepared["steps"][0]["capability"], "odoo.record.patch")
        self.assertEqual(
            prepared["steps"][0]["preview"]["changes"][0],
            {
                "field": "name",
                "before": "AI ACTION ORIGINAL",
                "after": "AI ACTION UPDATED",
            },
        )
        self.target.invalidate_recordset(["name"])
        self.assertEqual(self.target.name, "AI ACTION ORIGINAL")

        authorized = dict(prepared)
        authorized["state"] = "authorized"
        barrier_calls = []
        executed = asyncio.run(
            plans.execute(
                authorized,
                human_approved=True,
                before_effect=lambda: barrier_calls.append("crossed"),
            )
        )

        self.assertEqual(barrier_calls, ["crossed"])
        self.target.invalidate_recordset(["name"])
        self.assertEqual(self.target.name, "AI ACTION UPDATED")
        self.assertEqual(executed.payload["state"], "completed")
        self.assertEqual(executed.payload["steps"][0]["state"], "completed")
        self.assertIsNotNone(executed.payload["steps"][0]["verification"])
        self.assertIn("tool.preview.completed", [item[0] for item in events])
        self.assertIn("tool.completed", [item[0] for item in events])
        self.assertIn("tool.verify.completed", [item[0] for item in events])

    def test_mutation_after_preview_aborts_before_write_barrier(self):
        context, _registry, _executor, plans = self._runtime()
        prepared = asyncio.run(plans.prepare(self._planned_patch()))
        context.env["res.partner"].browse(self.target.id).write(
            {"name": "AI ACTION CHANGED AFTER PREVIEW"}
        )
        authorized = dict(prepared)
        authorized["state"] = "authorized"
        barrier_calls = []

        with self.assertRaises(CapabilityPlanError) as captured:
            asyncio.run(
                plans.execute(
                    authorized,
                    human_approved=True,
                    before_effect=lambda: barrier_calls.append("crossed"),
                )
            )

        self.assertEqual(captured.exception.code, "capability_plan_precondition_changed")
        self.assertEqual(barrier_calls, [])
        self.target.invalidate_recordset(["name"])
        self.assertEqual(self.target.name, "AI ACTION CHANGED AFTER PREVIEW")

    def test_tampered_arguments_fail_binding_before_write_barrier(self):
        _context, _registry, _executor, plans = self._runtime()
        prepared = asyncio.run(plans.prepare(self._planned_patch()))
        authorized = dict(prepared)
        authorized["state"] = "authorized"
        steps = [dict(item) for item in authorized["steps"]]
        steps[0]["arguments"] = {
            **steps[0]["arguments"],
            "values": {"name": "TAMPERED"},
        }
        authorized["steps"] = steps
        barrier_calls = []

        with self.assertRaises(CapabilityPlanError) as captured:
            asyncio.run(
                plans.execute(
                    authorized,
                    human_approved=True,
                    before_effect=lambda: barrier_calls.append("crossed"),
                )
            )

        self.assertEqual(captured.exception.code, "capability_plan_binding_mismatch")
        self.assertEqual(barrier_calls, [])
        self.target.invalidate_recordset(["name"])
        self.assertEqual(self.target.name, "AI ACTION ORIGINAL")

    def test_reject_is_terminal_and_never_writes(self):
        context, _registry, _executor, plans = self._runtime()
        prepared = asyncio.run(plans.prepare(self._planned_patch()))
        user_env = context.env
        queued = user_env["odoo.ai.turn"].enqueue_for_current_user(
            message="Cambia el nombre del contacto",
            screen={
                "action_id": None,
                "allowed_context_subset": {},
                "captured_at": "2026-08-26T00:00:00Z",
                "menu_id": None,
                "model": "res.partner",
                "res_id": self.target.id,
                "selected_ids": [],
                "view_type": "form",
            },
            client_request_id="action.reject.test.0001",
        )
        turn = user_env["odoo.ai.turn"]._owned_turn(queued["turn_id"])
        envelope = {
            "format_version": 1,
            "answer": "He preparado el cambio solicitado.",
            "confidence": "high",
            "human_approved": False,
            "plan": prepared,
        }
        policy = resolve_capability_policy(turn.policy_payload)
        response = user_env["odoo.ai.embedded.runtime"]._plan_response(
            turn,
            envelope,
            policy,
        )
        turn.with_user(SUPERUSER_ID).write(
            {
                "state": "awaiting_confirmation",
                "capability_plan_payload": envelope,
                "result_payload": response,
            }
        )

        decision = user_env["odoo.ai.turn"].decide_capability_plan_for_current_user(
            turn.turn_uuid,
            "reject",
        )

        turn.invalidate_recordset(["state", "result_payload", "capability_plan_payload"])
        self.assertEqual(decision["state"], "rejected")
        self.assertEqual(turn.state, "completed")
        self.assertEqual(turn.capability_plan_payload["plan"]["state"], "rejected")
        self.assertEqual(
            turn.result_payload["answer"],
            "Acción cancelada. No se ha realizado ningún cambio.",
        )
        self.target.invalidate_recordset(["name"])
        self.assertEqual(self.target.name, "AI ACTION ORIGINAL")

    def test_approve_requeues_same_turn_with_bound_authorization(self):
        context, _registry, _executor, plans = self._runtime()
        prepared = asyncio.run(plans.prepare(self._planned_patch()))
        user_env = context.env
        queued = user_env["odoo.ai.turn"].enqueue_for_current_user(
            message="Cambia el nombre del contacto",
            screen={
                "action_id": None,
                "allowed_context_subset": {},
                "captured_at": "2026-08-26T00:00:00Z",
                "menu_id": None,
                "model": "res.partner",
                "res_id": self.target.id,
                "selected_ids": [],
                "view_type": "form",
            },
            client_request_id="action.approve.test.0001",
        )
        turn = user_env["odoo.ai.turn"]._owned_turn(queued["turn_id"])
        envelope = {
            "format_version": 1,
            "answer": "He preparado el cambio solicitado.",
            "confidence": "high",
            "human_approved": False,
            "plan": prepared,
        }
        policy = resolve_capability_policy(turn.policy_payload)
        response = user_env["odoo.ai.embedded.runtime"]._plan_response(
            turn,
            envelope,
            policy,
        )
        turn.with_user(SUPERUSER_ID).write(
            {
                "state": "awaiting_confirmation",
                "capability_plan_payload": envelope,
                "result_payload": response,
            }
        )

        decision = user_env["odoo.ai.turn"].decide_capability_plan_for_current_user(
            turn.turn_uuid,
            "approve",
        )

        turn.invalidate_recordset(["state", "result_payload", "capability_plan_payload"])
        self.assertEqual(decision["state"], "authorized")
        self.assertEqual(turn.state, "queued")
        self.assertFalse(turn.result_payload)
        self.assertTrue(turn.capability_plan_payload["human_approved"])
        self.assertEqual(turn.capability_plan_payload["plan"]["state"], "authorized")
        self.target.invalidate_recordset(["name"])
        self.assertEqual(self.target.name, "AI ACTION ORIGINAL")
