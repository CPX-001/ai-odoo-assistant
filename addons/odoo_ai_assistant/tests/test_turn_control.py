import asyncio
from datetime import UTC, datetime

from odoo import SUPERUSER_ID, Command, fields
from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase

from ..models.turn_control import TurnControlError
from ..runtime.agent import CapabilityPlanService, PlannedCapability
from ..runtime.agent.compensation import (
    CapabilityCompensationError,
    CapabilityCompensationService,
    plan_is_compensatable,
)
from ..runtime.capabilities import (
    CapabilityConfigResolver,
    CapabilityContext,
    CapabilityExecutor,
    CapabilityPolicy,
    clear_discovery_cache,
    discover_capabilities,
)


class TestAssistantTurnControl(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        company = cls.env.company
        cls.user = cls.env["res.users"].create(
            {
                "name": "AI Turn Control User",
                "login": "ai-turn-control-user",
                "company_id": company.id,
                "company_ids": [Command.set([company.id])],
                "groups_id": [
                    Command.set(
                        [
                            cls.env.ref("base.group_user").id,
                            cls.env.ref("base.group_partner_manager").id,
                            cls.env.ref("base.group_system").id,
                        ]
                    )
                ],
            }
        )
        cls.other_company = cls.env["res.company"].create({"name": "AI Other Company"})
        cls.other_user = cls.env["res.users"].create(
            {
                "name": "AI Other Turn User",
                "login": "ai-other-turn-user",
                "company_id": cls.other_company.id,
                "company_ids": [Command.set([cls.other_company.id])],
                "groups_id": [Command.set([cls.env.ref("base.group_user").id])],
            }
        )

    def setUp(self):
        super().setUp()
        clear_discovery_cache()

    def _env(self):
        return self.env(user=self.user, su=False)

    def _screen(self, record_id=None):
        return {
            "action_id": None,
            "allowed_context_subset": {},
            "captured_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "menu_id": None,
            "model": "res.partner",
            "res_id": record_id,
            "selected_ids": [],
            "view_type": "form" if record_id else "list",
        }

    def _context(self, env, turn_id="turn-control-compensation"):
        return CapabilityContext(
            env=env,
            turn_id=turn_id,
            screen=self._screen(),
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

    def _plan_services(self, env, *, turn_id="turn-control-compensation"):
        context = self._context(env, turn_id)
        registry = discover_capabilities()
        executor = CapabilityExecutor(
            registry,
            context,
            policy=CapabilityPolicy(),
            config=CapabilityConfigResolver(),
        )
        return context, registry, executor, CapabilityPlanService(registry=registry, executor=executor)

    def test_redirects_are_durable_ordered_and_idempotent_on_same_turn(self):
        env = self._env()
        queued = env["odoo.ai.turn"].enqueue_for_current_user(
            message="Analiza los contactos",
            screen=self._screen(),
            client_request_id="turn.control.redirect.0001",
        )
        first_id = "ui:turn-control-redirect-0001"
        second_id = "ui:turn-control-redirect-0002"
        first = env["odoo.ai.turn"].redirect_for_current_user(
            queued["turn_id"], "Céntrate sólo en clientes", first_id
        )
        duplicate = env["odoo.ai.turn"].redirect_for_current_user(
            queued["turn_id"], "Céntrate sólo en clientes", first_id
        )
        second = env["odoo.ai.turn"].redirect_for_current_user(
            queued["turn_id"], "Y sólo los creados este mes", second_id
        )
        turn = env["odoo.ai.turn"]._owned_turn(queued["turn_id"])
        control = self.env["odoo.ai.turn.control"].with_user(SUPERUSER_ID).search(
            [("turn_ref_id", "=", turn.id)], limit=1
        )
        rows = self.env["odoo.ai.turn.intervention"].with_user(SUPERUSER_ID).search(
            [("turn_ref_id", "=", turn.id)], order="sequence"
        )

        self.assertEqual(first["turn_id"], queued["turn_id"])
        self.assertFalse(first["duplicate"])
        self.assertTrue(duplicate["duplicate"])
        self.assertEqual(duplicate["sequence"], first["sequence"])
        self.assertEqual(second["turn_id"], queued["turn_id"])
        self.assertEqual(control.intervention_sequence, 2)
        self.assertEqual(control.applied_sequence, 0)
        self.assertEqual(rows.mapped("sequence"), [1, 2])
        self.assertEqual(
            rows.mapped("message"),
            ["Céntrate sólo en clientes", "Y sólo los creados este mes"],
        )
        self.assertEqual(rows.mapped("client_intervention_id"), [first_id, second_id])
        self.assertTrue(all(row.state == "pending" for row in rows))

        with self.assertRaises(TurnControlError) as captured:
            env["odoo.ai.turn"].redirect_for_current_user(
                queued["turn_id"], "Contenido distinto", first_id
            )
        self.assertEqual(captured.exception.code, "turn_intervention_id_conflict")

    def test_redirect_is_isolated_by_user_company_conversation_and_turn(self):
        env = self._env()
        first = env["odoo.ai.turn"].enqueue_for_current_user(
            message="Primer chat",
            screen=self._screen(),
            client_request_id="turn.control.isolation.0001",
        )
        second = env["odoo.ai.turn"].enqueue_for_current_user(
            message="Segundo chat",
            screen=self._screen(),
            client_request_id="turn.control.isolation.0002",
        )
        env["odoo.ai.turn"].redirect_for_current_user(
            first["turn_id"], "Sólo primera conversación", "ui:turn-isolation-0001"
        )
        first_turn = env["odoo.ai.turn"]._owned_turn(first["turn_id"])
        second_turn = env["odoo.ai.turn"]._owned_turn(second["turn_id"])
        rows = self.env["odoo.ai.turn.intervention"].with_user(SUPERUSER_ID).search(
            [("turn_ref_id", "=", first_turn.id)]
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows.user_id, self.user)
        self.assertEqual(rows.company_id, self.user.company_id)
        self.assertEqual(rows.conversation_ref_id, first_turn.conversation_id.id)
        self.assertFalse(
            self.env["odoo.ai.turn.intervention"].with_user(SUPERUSER_ID).search(
                [("turn_ref_id", "=", second_turn.id)]
            )
        )

        other = self.env(user=self.other_user, su=False)
        with self.assertRaises(AccessError):
            other["odoo.ai.turn"].redirect_for_current_user(
                first["turn_id"], "No debo poder intervenir", "ui:turn-isolation-0002"
            )

    def test_effect_boundary_blocks_late_redirect(self):
        env = self._env()
        queued = env["odoo.ai.turn"].enqueue_for_current_user(
            message="Analiza los contactos",
            screen=self._screen(),
            client_request_id="turn.control.boundary.0001",
        )
        turn = env["odoo.ai.turn"]._owned_turn(queued["turn_id"])
        turn.with_user(SUPERUSER_ID).write({"state": "running", "write_barrier": True})
        with self.assertRaises(TurnControlError) as captured:
            env["odoo.ai.turn"].redirect_for_current_user(
                queued["turn_id"], "Nueva corrección tardía", "ui:turn-boundary-0001"
            )
        self.assertEqual(captured.exception.code, "turn_effect_already_committed")
        self.assertFalse(
            self.env["odoo.ai.turn.intervention"].with_user(SUPERUSER_ID).search(
                [("turn_ref_id", "=", turn.id)]
            )
        )

    def test_redirect_while_awaiting_approval_reuses_same_turn_and_rejects_old_plan(self):
        env = self._env()
        queued = env["odoo.ai.turn"].enqueue_for_current_user(
            message="Actualiza este contacto",
            screen=self._screen(),
            client_request_id="turn.control.approval.0001",
        )
        turn = env["odoo.ai.turn"]._owned_turn(queued["turn_id"])
        old_message = self.env["odoo.ai.message"].with_user(SUPERUSER_ID).create(
            {
                "conversation_id": turn.conversation_id.id,
                "role": "assistant",
                "content": "Confirma la operación propuesta",
                "internal_workflow": "AGENT",
            }
        )
        turn.with_user(SUPERUSER_ID).write(
            {
                "state": "awaiting_confirmation",
                "assistant_message_id": old_message.id,
                "capability_plan_payload": {
                    "format_version": 1,
                    "answer": "Plan anterior",
                    "confidence": "high",
                    "human_approved": False,
                    "plan": {"state": "awaiting_confirmation"},
                },
                "result_payload": {"old": True},
                "working_items_payload": [],
            }
        )

        redirected = env["odoo.ai.turn"].redirect_for_current_user(
            turn.turn_uuid,
            "No, cambia sólo el teléfono",
            "ui:turn-approval-0001",
        )

        turn.invalidate_recordset(
            [
                "state",
                "capability_plan_payload",
                "result_payload",
                "assistant_message_id",
                "working_items_payload",
            ]
        )
        self.assertEqual(redirected["turn_id"], queued["turn_id"])
        self.assertEqual(redirected["state"], "queued")
        self.assertEqual(turn.state, "queued")
        self.assertFalse(turn.capability_plan_payload)
        self.assertFalse(turn.result_payload)
        self.assertFalse(turn.assistant_message_id)
        self.assertFalse(turn.working_items_payload)
        self.assertTrue(old_message.exists())
        self.assertEqual(redirected["message"]["content"], "No, cambia sólo el teléfono")
        rejection = self.env["odoo.ai.turn.event"].with_user(SUPERUSER_ID).search(
            [("turn_id", "=", turn.id), ("event_type", "=", "approval.rejected")], limit=1
        )
        self.assertTrue(rejection)

    def test_stop_returns_partial_interrupted_answer_and_does_not_touch_another_chat(self):
        env = self._env()
        first = env["odoo.ai.turn"].enqueue_for_current_user(
            message="Primera petición larga",
            screen=self._screen(),
            client_request_id="turn.control.stop.0001",
        )
        second = env["odoo.ai.turn"].enqueue_for_current_user(
            message="Segundo chat independiente",
            screen=self._screen(),
            client_request_id="turn.control.stop.0002",
        )
        turn = env["odoo.ai.turn"]._owned_turn(first["turn_id"])
        turn.with_user(SUPERUSER_ID).write(
            {"state": "running", "lease_token": "turn-control-stop-lease"}
        )
        self.env["odoo.ai.turn.live.event"].with_user(SUPERUSER_ID).create(
            {
                "turn_ref_id": turn.id,
                "turn_uuid": turn.turn_uuid,
                "user_id": turn.user_id.id,
                "company_id": turn.company_id.id,
                "sequence": 1,
                "channel": "answer",
                "answer_delta": "Respuesta parcial ya visible",
                "occurred_at": fields.Datetime.now(),
            }
        )

        status = env["odoo.ai.turn"].cancel_for_current_user(first["turn_id"])

        self.assertEqual(status["state"], "cancel_requested")
        self.assertEqual(status["answer"], "Respuesta parcial ya visible\n\n— Interrumpido")
        other = env["odoo.ai.turn"]._owned_turn(second["turn_id"])
        self.assertEqual(other.state, "queued")
        other_control = self.env["odoo.ai.turn.control"].with_user(SUPERUSER_ID).search(
            [("turn_ref_id", "=", other.id)], limit=1
        )
        self.assertFalse(other_control)

    def test_patch_compensation_is_host_only_conflict_safe_and_verified(self):
        env = self._env()
        target = env["res.partner"].create({"name": "BEFORE"})
        context, registry, executor, plans = self._plan_services(env)
        host_names = {item.name for item in registry.for_host(context)}
        model_names = {item["name"] for item in registry.model_catalog(context)}
        self.assertIn("odoo.record.patch.revert", host_names)
        self.assertNotIn("odoo.record.patch.revert", model_names)
        requested = (
            PlannedCapability(
                capability="odoo.record.patch",
                arguments={
                    "model": "res.partner",
                    "record_id": target.id,
                    "values": {"name": "AFTER"},
                },
                summary="Actualizar contacto",
            ),
        )
        prepared = asyncio.run(plans.prepare(requested))
        executed = asyncio.run(
            plans.execute({**prepared, "state": "authorized"}, human_approved=True)
        )
        self.assertTrue(plan_is_compensatable(registry, context, executed.payload))

        queued = env["odoo.ai.turn"].enqueue_for_current_user(
            message="Actualiza el contacto",
            screen=self._screen(target.id),
            client_request_id="turn.control.revert.0001",
        )
        turn = env["odoo.ai.turn"]._owned_turn(queued["turn_id"])
        envelope = {
            "format_version": 1,
            "answer": "Cambio completado.",
            "confidence": "high",
            "human_approved": True,
            "plan": executed.payload,
        }
        turn.with_user(SUPERUSER_ID).write(
            {
                "state": "completed",
                "write_barrier": True,
                "capability_plan_payload": envelope,
                "reversion_state": "available",
            }
        )
        response = env["odoo.ai.embedded.runtime"]._plan_response(
            turn,
            envelope,
            {
                "confirmation_mode": "always_confirm",
                "max_auto_risk": "low",
                "allow_synthetic_data": False,
            },
        )
        turn.with_user(SUPERUSER_ID).write({"result_payload": response})

        target.write({"name": "LATER CHANGE"})
        with self.assertRaises(TurnControlError) as captured:
            env["odoo.ai.turn"].revert_for_current_user(turn.turn_uuid)
        self.assertEqual(captured.exception.code, "capability_compensation_precondition_changed")
        self.assertEqual(target.name, "LATER CHANGE")

        target.write({"name": "AFTER"})
        reverted = env["odoo.ai.turn"].revert_for_current_user(turn.turn_uuid)
        target.invalidate_recordset(["name"])
        turn.invalidate_recordset(["reversion_state"])
        self.assertEqual(target.name, "BEFORE")
        self.assertEqual(turn.reversion_state, "completed")
        self.assertEqual(reverted["response"]["plan"]["metadata"]["reversion_state"], "completed")

    def test_archive_and_unarchive_have_explicit_verified_compensators(self):
        env = self._env()
        context, registry, executor, plans = self._plan_services(
            env, turn_id="turn-control-archive-compensation"
        )
        for capability, initial, effected, restored in (
            ("odoo.record.archive", True, False, True),
            ("odoo.record.unarchive", False, True, False),
        ):
            target = env["res.partner"].with_context(active_test=False).create(
                {"name": f"Target {capability}", "active": initial}
            )
            requested = (
                PlannedCapability(
                    capability=capability,
                    arguments={"model": "res.partner", "record_id": target.id},
                    summary=capability,
                ),
            )
            prepared = asyncio.run(plans.prepare(requested))
            executed = asyncio.run(
                plans.execute({**prepared, "state": "authorized"}, human_approved=True)
            )
            target.invalidate_recordset(["active"])
            self.assertEqual(target.active, effected)
            self.assertTrue(plan_is_compensatable(registry, context, executed.payload))
            compensation = CapabilityCompensationService(
                registry=registry, context=context, executor=executor
            )
            result = asyncio.run(compensation.compensate(executed.payload))
            target.invalidate_recordset(["active"])
            self.assertEqual(target.active, restored)
            self.assertTrue(result.results[0].data["verified"])

    def test_compensation_revalidates_current_write_rules_and_fails_closed(self):
        env = self._env()
        target = env["res.partner"].create({"name": "BEFORE PERMISSION"})
        context, registry, executor, plans = self._plan_services(
            env, turn_id="turn-control-permission-compensation"
        )
        requested = (
            PlannedCapability(
                capability="odoo.record.patch",
                arguments={
                    "model": "res.partner",
                    "record_id": target.id,
                    "values": {"name": "AFTER PERMISSION"},
                },
                summary="Actualizar contacto",
            ),
        )
        prepared = asyncio.run(plans.prepare(requested))
        executed = asyncio.run(
            plans.execute({**prepared, "state": "authorized"}, human_approved=True)
        )
        self.assertEqual(target.name, "AFTER PERMISSION")

        self.env["ir.rule"].create(
            {
                "name": "AI compensation write deny",
                "model_id": self.env["ir.model"]._get_id("res.partner"),
                "domain_force": "[('id', '=', 0)]",
                "perm_read": False,
                "perm_write": True,
                "perm_create": False,
                "perm_unlink": False,
            }
        )
        compensation = CapabilityCompensationService(
            registry=registry, context=context, executor=executor
        )
        with self.assertRaises(CapabilityCompensationError) as captured:
            asyncio.run(compensation.compensate(executed.payload))
        self.assertIn(
            captured.exception.code,
            {"access_denied", "capability_compensation_rejected"},
        )
        self.assertEqual(target.name, "AFTER PERMISSION")
