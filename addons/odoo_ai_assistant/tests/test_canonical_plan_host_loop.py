import asyncio
from dataclasses import replace

from odoo import Command
from odoo.tests.common import TransactionCase

from ..runtime.agent.contracts import FinalAnswer, PlanStepProposal, TaskPlanUpdate
from ..runtime.agent.decision_validation import (
    NextDecisionValidationError,
    RejectedTaskPlanUpdate,
)
from ..runtime.agent.plan import CapabilityPlanService
from ..runtime.agent.planning import PlanningDecisionEngine, resolve_planning_strategy
from ..runtime.agent.service import AgentTurnError, AgentTurnService
from ..runtime.agent.task_plan import TaskPlan, TaskPlanStep
from ..runtime.agent.working_transcript import append_working_item
from ..runtime.capabilities import (
    CapabilityConfigResolver,
    CapabilityContext,
    CapabilityExecutor,
    CapabilityPolicy,
    discover_capabilities,
)


class _PlanDecisionEngine:
    def __init__(self, *decisions):
        self.decisions = list(decisions)
        self.calls = 0
        self.working_items = []

    async def next_decision(self, **kwargs):
        self.calls += 1
        self.working_items.append(kwargs.get("working_items", ()))
        if not self.decisions:
            raise AssertionError("unexpected provider decision request")
        return self.decisions.pop(0)


class _MalformedPlanThenAnswerEngine:
    def __init__(self):
        self.calls = 0

    async def next_decision(self, **kwargs):
        del kwargs
        self.calls += 1
        if self.calls == 1:
            raise NextDecisionValidationError(
                "agent_task_plan_revision_invalid",
                RejectedTaskPlanUpdate(rejected_revision=2),
            )
        return FinalAnswer("final_answer", "Respuesta corregida", "high")


class TestCanonicalPlanHostLoop(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        internal = cls.env.ref("base.group_user")
        partner_manager = cls.env.ref("base.group_partner_manager")
        system = cls.env.ref("base.group_system")
        company = cls.env.company
        cls.action_user = cls.env["res.users"].create(
            {
                "name": "Canonical Plan User",
                "login": "canonical-plan-user",
                "company_id": company.id,
                "company_ids": [Command.set([company.id])],
                "groups_id": [Command.set([internal.id, partner_manager.id, system.id])],
            }
        )

    def setUp(self):
        super().setUp()
        self.target = self.env["res.partner"].create({"name": "CANONICAL PLAN ORIGINAL"})

    def _runtime(self):
        env = self.env(user=self.action_user, su=False)
        context = CapabilityContext(
            env=env,
            turn_id="canonical-plan-test",
            screen={"model": "res.partner", "res_id": self.target.id},
            metadata={
                "capability_policy": {
                    "confirmation_mode": "always_confirm",
                    "max_auto_risk": "low",
                    "max_provider_decisions": 12,
                    "max_capability_calls": 8,
                    "max_consecutive_correctable_failures": 3,
                    "max_write_steps_per_plan": 12,
                    "max_effect_steps_per_plan": 5,
                }
            },
        )
        registry = discover_capabilities()
        executor = self._executor(registry, context)
        return context, registry, executor, CapabilityPlanService(
            registry=registry,
            executor=executor,
        )

    def _executor(self, registry, context):
        return CapabilityExecutor(
            registry,
            context,
            policy=CapabilityPolicy(),
            config=CapabilityConfigResolver(),
        )

    def _context_with_metadata(
        self,
        context,
        registry,
        *,
        policy_updates=None,
        planning_strategy=None,
    ):
        metadata = {key: value for key, value in context.metadata.items()}
        if policy_updates:
            policy = dict(metadata.get("capability_policy") or {})
            policy.update(policy_updates)
            metadata["capability_policy"] = policy
        if planning_strategy is not None:
            metadata["planning_strategy"] = planning_strategy
        updated = replace(context, metadata=metadata)
        return updated, self._executor(registry, updated)

    def _service(self, registry, context, executor, *decisions):
        engine = _PlanDecisionEngine(*decisions)
        service = AgentTurnService(
            registry=registry,
            context=context,
            executor=executor,
            decision_engine=engine,
            allow_plan_proposals=True,
        )
        return engine, service

    def test_unparseable_task_plan_revision_is_corrected_in_the_same_service_loop(self):
        context, registry, executor, _plans = self._runtime()
        engine = _MalformedPlanThenAnswerEngine()
        service = AgentTurnService(
            registry=registry,
            context=context,
            executor=executor,
            decision_engine=engine,
            allow_plan_proposals=True,
        )

        result = asyncio.run(service.run(message="Crea 30 presupuestos"))

        self.assertEqual(result.answer, "Respuesta corregida")
        self.assertEqual(engine.calls, 2)
        errors = [item for item in service.working_items if item.kind == "task_plan_error"]
        self.assertEqual(len(errors), 1)
        self.assertEqual(
            errors[0].data,
            {
                "code": "agent_task_plan_revision_invalid",
                "rejected_revision": 2,
            },
        )

    def test_rolled_back_plan_starts_a_fresh_bounded_plan_epoch(self):
        context, registry, executor, _plans = self._runtime()
        old_arguments = {
            "model": "res.partner",
            "record_id": self.target.id,
            "values": {"name": "STALE PLAN"},
        }
        items = append_working_item((), "user_input", {"message": "Actualiza"})
        items = append_working_item(
            items,
            "assistant_decision",
            {
                "call_id": "old-step",
                "decision_kind": "plan_step_proposal",
                "capability": "odoo.record.patch",
                "arguments": old_arguments,
                "summary": "Plan anterior",
            },
        )
        items = append_working_item(
            items,
            "plan_step_proposed",
            {
                "call_id": "old-step",
                "capability": "odoo.record.patch",
                "arguments": old_arguments,
                "summary": "Plan anterior",
            },
        )
        items = append_working_item(
            items,
            "final_answer",
            {"answer": "Plan anterior", "confidence": "high"},
        )
        items = append_working_item(
            items,
            "plan_execution_error",
            {
                "code": "action_rejected",
                "step_id": "old-step",
                "capability": "odoo.record.patch",
                "details": {"model": "res.partner"},
                "effect_state": "none",
                "rolled_back": True,
                "replan": 1,
            },
        )
        new_arguments = {
            "model": "res.partner",
            "record_id": self.target.id,
            "values": {"name": "REPAIRED PLAN"},
        }
        engine = _PlanDecisionEngine(
            PlanStepProposal(
                "plan_step_proposal",
                "new-step",
                "odoo.record.patch",
                new_arguments,
                "Plan corregido",
            ),
            FinalAnswer("final_answer", "Plan corregido", "high"),
        )
        service = AgentTurnService(
            registry=registry,
            context=context,
            executor=executor,
            decision_engine=engine,
            working_items=items,
            allow_plan_proposals=True,
        )

        result = asyncio.run(service.run(message="Actualiza"))

        self.assertEqual(engine.calls, 2)
        self.assertEqual([step.step_id for step in result.plan], ["new-step"])
        self.assertEqual(result.plan[0].arguments, new_arguments)

    def test_patch_proposal_is_stage_only_until_approved_then_executes_once_and_verifies(self):
        context, registry, executor, plans = self._runtime()
        proposal = PlanStepProposal(
            "plan_step_proposal",
            "patch-1",
            "odoo.record.patch",
            {
                "model": "res.partner",
                "record_id": self.target.id,
                "values": {"name": "CANONICAL PLAN UPDATED"},
            },
            "Cambiar el nombre del contacto",
        )
        engine, service = self._service(
            registry,
            context,
            executor,
            proposal,
            FinalAnswer("final_answer", "Plan preparado", "high"),
        )
        result = asyncio.run(service.run(message="Cambia el nombre del contacto"))
        self.assertFalse(context.env.su)
        self.assertEqual(len(result.plan), 1)
        self.assertEqual(result.plan[0].capability, "odoo.record.patch")
        self.assertEqual(result.plan[0].step_id, "patch-1")
        self.assertEqual(engine.calls, 2)
        self.target.invalidate_recordset(["name"])
        self.assertEqual(self.target.name, "CANONICAL PLAN ORIGINAL")

        prepared = asyncio.run(plans.prepare(result.plan))
        self.assertEqual(prepared["format_version"], 3)
        self.assertEqual(prepared["state"], "awaiting_confirmation")
        self.assertTrue(prepared["requires_confirmation"])
        self.assertEqual(prepared["steps"][0]["step_id"], "patch-1")
        self.assertEqual(prepared["steps"][0]["recovery_mode"], "odoo_atomic")
        self.assertEqual(prepared["steps"][0]["journal_classification"], "reversible")
        self.assertEqual(
            prepared["recovery_units"],
            [
                {
                    "unit_id": "unit-1",
                    "mode": "odoo_atomic",
                    "step_ids": ["patch-1"],
                    "state": "prepared",
                }
            ],
        )
        self.assertEqual(
            prepared["steps"][0]["preview"]["changes"][0],
            {
                "field": "name",
                "before": "CANONICAL PLAN ORIGINAL",
                "after": "CANONICAL PLAN UPDATED",
            },
        )
        self.target.invalidate_recordset(["name"])
        self.assertEqual(self.target.name, "CANONICAL PLAN ORIGINAL")

        authorized = dict(prepared)
        authorized["state"] = "authorized"
        barrier = []
        executed = asyncio.run(
            plans.execute(
                authorized,
                human_approved=True,
                before_effect=lambda: barrier.append("crossed"),
            )
        )
        self.assertEqual(barrier, ["crossed"])
        self.target.invalidate_recordset(["name"])
        self.assertEqual(self.target.name, "CANONICAL PLAN UPDATED")
        self.assertEqual(executed.payload["state"], "completed")
        self.assertEqual(executed.payload["recovery_units"][0]["state"], "completed")
        self.assertIsNotNone(executed.payload["steps"][0]["verification"])

    def test_create_proposal_does_not_create_before_approval_and_verifies_one_record(self):
        context, registry, executor, plans = self._runtime()
        marker = "CANONICAL CREATE FIXTURE"
        proposal = PlanStepProposal(
            "plan_step_proposal",
            "create-1",
            "odoo.record.create",
            {"model": "res.partner", "values": {"name": marker}},
            "Crear contacto",
        )
        _engine, service = self._service(
            registry,
            context,
            executor,
            proposal,
            FinalAnswer("final_answer", "Plan preparado", "high"),
        )
        result = asyncio.run(service.run(message="Crea un contacto"))
        self.assertEqual(context.env["res.partner"].search_count([("name", "=", marker)]), 0)
        prepared = asyncio.run(plans.prepare(result.plan))
        self.assertEqual(prepared["steps"][0]["journal_classification"], "reconstructable")
        self.assertEqual(context.env["res.partner"].search_count([("name", "=", marker)]), 0)
        authorized = dict(prepared)
        authorized["state"] = "authorized"
        executed = asyncio.run(
            plans.execute(authorized, human_approved=True, before_effect=lambda: None)
        )
        self.assertEqual(context.env["res.partner"].search_count([("name", "=", marker)]), 1)
        self.assertEqual(executed.payload["state"], "completed")
        self.assertIsNotNone(executed.payload["steps"][0]["verification"])

    def test_two_independent_patches_form_one_ordered_atomic_recovery_unit(self):
        context, registry, executor, plans = self._runtime()
        second = self.env["res.partner"].create({"name": "CANONICAL PLAN SECOND"})
        decisions = (
            PlanStepProposal(
                "plan_step_proposal",
                "patch-a",
                "odoo.record.patch",
                {
                    "model": "res.partner",
                    "record_id": self.target.id,
                    "values": {"name": "CANONICAL PLAN A"},
                },
                "Actualizar primer contacto",
            ),
            PlanStepProposal(
                "plan_step_proposal",
                "patch-b",
                "odoo.record.patch",
                {
                    "model": "res.partner",
                    "record_id": second.id,
                    "values": {"name": "CANONICAL PLAN B"},
                },
                "Actualizar segundo contacto",
            ),
            FinalAnswer("final_answer", "Dos cambios preparados", "high"),
        )
        engine, service = self._service(registry, context, executor, *decisions)
        result = asyncio.run(service.run(message="Actualiza ambos contactos"))
        self.assertEqual(engine.calls, 3)
        self.assertEqual(len(result.plan), 2)
        self.assertEqual(result.plan[0].depends_on, ())
        self.assertEqual(result.plan[1].depends_on, ("patch-a",))

        prepared = asyncio.run(plans.prepare(result.plan))
        self.assertEqual(len(prepared["steps"]), 2)
        self.assertEqual(prepared["steps"][1]["depends_on"], ["patch-a"])
        self.assertEqual(len(prepared["recovery_units"]), 1)
        self.assertEqual(prepared["recovery_units"][0]["mode"], "odoo_atomic")
        self.assertEqual(
            prepared["recovery_units"][0]["step_ids"],
            ["patch-a", "patch-b"],
        )
        self.assertTrue(
            all(step["journal_classification"] == "reversible" for step in prepared["steps"])
        )
        authorized = dict(prepared)
        authorized["state"] = "authorized"
        barriers = []
        executed = asyncio.run(
            plans.execute(
                authorized,
                human_approved=True,
                before_effect=lambda: barriers.append("crossed"),
            )
        )
        self.assertEqual(barriers, ["crossed"])
        self.target.invalidate_recordset(["name"])
        second.invalidate_recordset(["name"])
        self.assertEqual(self.target.name, "CANONICAL PLAN A")
        self.assertEqual(second.name, "CANONICAL PLAN B")
        self.assertEqual(len(executed.results), 2)
        self.assertTrue(all(step["verification"] for step in executed.payload["steps"]))

    def test_task_plan_revision_is_durable_progress_separate_from_two_effect_steps(self):
        context, registry, executor, _plans = self._runtime()
        second = self.env["res.partner"].create({"name": "TASK PLAN SECOND"})
        task_v1 = TaskPlanUpdate(
            "task_plan_update",
            TaskPlan(
                goal="Actualizar los dos contactos",
                revision=1,
                steps=(
                    TaskPlanStep("inspect", "Preparar cambios", "completed"),
                    TaskPlanStep("apply", "Preparar acciones", "in_progress", ("inspect",)),
                ),
            ),
        )
        task_v2 = TaskPlanUpdate(
            "task_plan_update",
            TaskPlan(
                goal="Actualizar los dos contactos",
                revision=2,
                steps=(
                    TaskPlanStep("inspect", "Preparar cambios", "completed"),
                    TaskPlanStep("apply", "Preparar acciones", "completed", ("inspect",)),
                ),
            ),
        )
        engine, service = self._service(
            registry,
            context,
            executor,
            task_v1,
            PlanStepProposal(
                "plan_step_proposal",
                "patch-a",
                "odoo.record.patch",
                {
                    "model": "res.partner",
                    "record_id": self.target.id,
                    "values": {"name": "TASK PLAN A"},
                },
                "Actualizar primer contacto",
            ),
            PlanStepProposal(
                "plan_step_proposal",
                "patch-b",
                "odoo.record.patch",
                {
                    "model": "res.partner",
                    "record_id": second.id,
                    "values": {"name": "TASK PLAN B"},
                },
                "Actualizar segundo contacto",
            ),
            task_v2,
            FinalAnswer("final_answer", "Plan preparado", "high"),
        )

        result = asyncio.run(service.run(message="Actualiza ambos contactos"))

        self.assertEqual(engine.calls, 5)
        self.assertEqual(len(result.plan), 2)
        self.assertIsNotNone(result.task_plan)
        self.assertEqual(result.task_plan.revision, 2)
        self.assertEqual(result.task_plan.steps[-1].state, "completed")
        task_items = [item for item in service.working_items if item.kind == "task_plan"]
        self.assertEqual([item.data["revision"] for item in task_items], [1, 2])
        self.assertTrue(all("capability" not in item.data for item in task_items))
        self.target.invalidate_recordset(["name"])
        second.invalidate_recordset(["name"])
        self.assertEqual(self.target.name, "CANONICAL PLAN ORIGINAL")
        self.assertEqual(second.name, "TASK PLAN SECOND")

    def test_task_plan_revision_must_increment_exactly_once(self):
        context, registry, executor, _plans = self._runtime()
        engine, service = self._service(
            registry,
            context,
            executor,
            TaskPlanUpdate(
                "task_plan_update",
                TaskPlan(
                    goal="Resolver",
                    revision=1,
                    steps=(TaskPlanStep("one", "Primero", "in_progress"),),
                ),
            ),
            TaskPlanUpdate(
                "task_plan_update",
                TaskPlan(
                    goal="Resolver",
                    revision=3,
                    steps=(TaskPlanStep("one", "Primero", "completed"),),
                ),
            ),
        )

        with self.assertRaises(AgentTurnError) as captured:
            asyncio.run(service.run(message="Resuelve"))

        self.assertEqual(captured.exception.code, "agent_task_plan_revision_invalid")
        self.assertEqual(engine.calls, 2)

    def test_noop_task_plan_progress_is_correctable_and_not_published(self):
        context, registry, executor, _plans = self._runtime()
        strategy = resolve_planning_strategy(
            "deliberate",
            message="Resuelve",
            screen=context.screen,
        ).payload()
        context, executor = self._context_with_metadata(
            context,
            registry,
            planning_strategy=strategy,
        )
        initial = TaskPlan(
            goal="Resolver",
            revision=1,
            steps=(
                TaskPlanStep("one", "Primero", "in_progress"),
                TaskPlanStep("two", "Después", "pending", ("one",)),
            ),
        )
        duplicate = TaskPlan(
            goal="Resolver",
            revision=2,
            steps=(
                TaskPlanStep("one", "Primero", "in_progress"),
                TaskPlanStep("two", "Después", "pending", ("one",)),
            ),
        )
        underlying = _PlanDecisionEngine(
            TaskPlanUpdate("task_plan_update", initial),
            TaskPlanUpdate("task_plan_update", duplicate),
            FinalAnswer("final_answer", "Continúo sin simular progreso.", "high"),
        )
        service = AgentTurnService(
            registry=registry,
            context=context,
            executor=executor,
            decision_engine=PlanningDecisionEngine(underlying),
            allow_plan_proposals=True,
        )

        result = asyncio.run(service.run(message="Resuelve"))

        self.assertEqual(result.answer, "Continúo sin simular progreso.")
        self.assertEqual(underlying.calls, 3)
        task_items = [item for item in service.working_items if item.kind == "task_plan"]
        self.assertEqual([item.data["revision"] for item in task_items], [1])
        errors = [item for item in service.working_items if item.kind == "task_plan_error"]
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0].data["code"], "agent_task_plan_progress_required")
        self.assertFalse(
            underlying.working_items[2][-1]["data"]["task_plan_available"]
        )

    def test_task_plan_updates_do_not_reset_provider_decision_budget(self):
        context, registry, executor, _plans = self._runtime()
        strategy = resolve_planning_strategy(
            "deliberate",
            message="Resuelve",
            screen=context.screen,
        ).payload()
        context, executor = self._context_with_metadata(
            context,
            registry,
            policy_updates={"max_provider_decisions": 2},
            planning_strategy=strategy,
        )
        initial = TaskPlan(
            goal="Resolver",
            revision=1,
            steps=(TaskPlanStep("one", "Primero", "in_progress"),),
        )
        progress = TaskPlan(
            goal="Resolver",
            revision=2,
            steps=(TaskPlanStep("one", "Primero", "completed"),),
            revision_kind="progress",
            revision_summary="Paso completado.",
        )
        underlying = _PlanDecisionEngine(
            TaskPlanUpdate("task_plan_update", initial),
            TaskPlanUpdate("task_plan_update", progress),
            FinalAnswer("final_answer", "No debe alcanzarse.", "high"),
        )
        service = AgentTurnService(
            registry=registry,
            context=context,
            executor=executor,
            decision_engine=PlanningDecisionEngine(underlying),
            allow_plan_proposals=True,
        )

        result = asyncio.run(service.run(message="Resuelve"))

        self.assertEqual(result.plan, ())
        self.assertEqual(result.confidence, "low")
        self.assertEqual(
            service.working_items[-1].data["host_fallback_code"],
            "agent_provider_decision_budget_exceeded",
        )
        self.assertEqual(underlying.calls, 2)
        self.assertEqual(
            [item.data["revision"] for item in service.working_items if item.kind == "task_plan"],
            [1, 2],
        )

    def test_task_plan_retry_cannot_evade_consecutive_failure_budget(self):
        context, registry, executor, _plans = self._runtime()
        strategy = resolve_planning_strategy(
            "deliberate",
            message="Resuelve",
            screen=context.screen,
        ).payload()
        context, executor = self._context_with_metadata(
            context,
            registry,
            policy_updates={
                "max_consecutive_failures": 1,
                "max_consecutive_correctable_failures": 1,
            },
            planning_strategy=strategy,
        )
        initial = TaskPlan(
            goal="Resolver",
            revision=1,
            steps=(TaskPlanStep("one", "Primero", "in_progress"),),
        )
        duplicate = TaskPlan(
            goal="Resolver",
            revision=2,
            steps=(TaskPlanStep("one", "Primero", "in_progress"),),
            revision_kind="progress",
        )
        underlying = _PlanDecisionEngine(
            TaskPlanUpdate("task_plan_update", initial),
            TaskPlanUpdate("task_plan_update", duplicate),
            TaskPlanUpdate("task_plan_update", duplicate),
        )
        service = AgentTurnService(
            registry=registry,
            context=context,
            executor=executor,
            decision_engine=PlanningDecisionEngine(underlying),
            allow_plan_proposals=True,
        )

        result = asyncio.run(service.run(message="Resuelve"))

        self.assertEqual(result.plan, ())
        self.assertEqual(
            service.working_items[-1].data["host_fallback_code"],
            "agent_correctable_failure_budget_exceeded",
        )
        self.assertEqual(underlying.calls, 3)
        errors = [item for item in service.working_items if item.kind == "task_plan_error"]
        self.assertEqual(
            [item.data["code"] for item in errors],
            ["agent_task_plan_progress_required", "agent_task_plan_not_useful"],
        )
