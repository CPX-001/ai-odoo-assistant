import asyncio
from datetime import UTC, datetime, timedelta

from odoo import SUPERUSER_ID, Command, fields
from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase

from ..runtime.agent import CapabilityPlanService, PlannedCapability
from ..runtime.capabilities import (
    CapabilityConfigResolver,
    CapabilityContext,
    CapabilityExecutor,
    CapabilityPolicy,
    clear_discovery_cache,
    discover_capabilities,
)


class TestAssistantEffectJournal(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        company = cls.env.company
        cls.user = cls.env["res.users"].create(
            {
                "name": "AI Effect Journal User",
                "login": "ai-effect-journal-user",
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
        cls.other_user = cls.env["res.users"].create(
            {
                "name": "AI Effect Journal Other User",
                "login": "ai-effect-journal-other-user",
                "company_id": company.id,
                "company_ids": [Command.set([company.id])],
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

    def _turn(self, env, suffix, record_id=None):
        queued = env["odoo.ai.turn"].enqueue_for_current_user(
            message=f"Effect journal {suffix}",
            screen=self._screen(record_id),
            client_request_id=f"effect.journal.{suffix}.0001",
        )
        return env["odoo.ai.turn"]._owned_turn(queued["turn_id"])

    def _plans(self, env, turn):
        context = CapabilityContext(
            env=env,
            turn_id=turn.turn_uuid,
            conversation_id=turn.conversation_id.conversation_uuid,
            screen=turn.screen_payload or {},
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
        executor = CapabilityExecutor(
            registry,
            context,
            policy=CapabilityPolicy(),
            config=CapabilityConfigResolver(),
        )
        return CapabilityPlanService(registry=registry, executor=executor)

    def test_patch_create_delete_get_conservative_journal_classes_and_sanitized_browser_rows(self):
        env = self._env()
        target = env["res.partner"].create({"name": "JOURNAL TARGET"})
        journal = self.env["odoo.ai.effect.journal"].with_user(SUPERUSER_ID)
        cases = (
            (
                "patch",
                PlannedCapability(
                    "odoo.record.patch",
                    {
                        "model": "res.partner",
                        "record_id": target.id,
                        "values": {"name": "JOURNAL PATCHED"},
                    },
                    "Actualizar contacto",
                    "patch-1",
                ),
                "reversible",
            ),
            (
                "create",
                PlannedCapability(
                    "odoo.record.create",
                    {"model": "res.partner", "values": {"name": "JOURNAL CREATED"}},
                    "Crear contacto",
                    "create-1",
                ),
                "reconstructable",
            ),
            (
                "delete",
                PlannedCapability(
                    "odoo.record.delete",
                    {"model": "res.partner", "record_id": target.id},
                    "Eliminar contacto",
                    "delete-1",
                ),
                "irreversible",
            ),
        )

        turns = []
        for suffix, requested, expected in cases:
            turn = self._turn(env, suffix, target.id)
            prepared = asyncio.run(self._plans(env, turn).prepare((requested,)))
            self.assertEqual(prepared["format_version"], 3)
            self.assertEqual(prepared["steps"][0]["journal_classification"], expected)
            journal._sync_plan(turn, prepared)
            row = journal.search([("turn_id", "=", turn.id)], limit=1)
            self.assertEqual(row.classification, expected)
            self.assertEqual(row.recovery_mode, "odoo_atomic")
            self.assertEqual(row.state, "prepared")
            turns.append(turn)

        visible = env["odoo.ai.turn"].effect_journal_for_current_user(turns[0].turn_uuid)
        self.assertEqual(len(visible["entries"]), 1)
        entry = visible["entries"][0]
        self.assertEqual(entry["classification"], "reversible")
        self.assertTrue(entry["reversible"])
        self.assertNotIn("before_payload", entry)
        self.assertNotIn("after_payload", entry)
        self.assertNotIn("receipt_payload", entry)

        other_env = self.env(user=self.other_user, su=False)
        with self.assertRaises(AccessError):
            other_env["odoo.ai.turn"].effect_journal_for_current_user(turns[0].turn_uuid)

    def test_failure_marks_internal_inflight_unit_rolled_back_and_external_uncertain(self):
        env = self._env()
        target = env["res.partner"].create({"name": "JOURNAL FAILURE"})
        journal = self.env["odoo.ai.effect.journal"].with_user(SUPERUSER_ID)

        internal_turn = self._turn(env, "internal-failure", target.id)
        prepared = asyncio.run(
            self._plans(env, internal_turn).prepare(
                (
                    PlannedCapability(
                        "odoo.record.patch",
                        {
                            "model": "res.partner",
                            "record_id": target.id,
                            "values": {"name": "NEVER COMMITTED"},
                        },
                        "Actualizar contacto",
                        "internal-step",
                    ),
                )
            )
        )
        prepared["state"] = "executing"
        prepared["recovery_units"][0]["state"] = "executing"
        journal._sync_plan(internal_turn, prepared)
        internal_turn.with_user(SUPERUSER_ID).write(
            {
                "capability_plan_payload": {
                    "format_version": 1,
                    "answer": "",
                    "confidence": "high",
                    "human_approved": True,
                    "plan": prepared,
                }
            }
        )
        journal._mark_turn_failure(internal_turn)
        internal_row = journal.search([("turn_id", "=", internal_turn.id)], limit=1)
        self.assertEqual(internal_row.state, "rolled_back")

        external_turn = self._turn(env, "external-failure", target.id)
        external = {**prepared, "steps": [dict(prepared["steps"][0])], "recovery_units": []}
        external["steps"][0]["step_id"] = "external-step"
        external["steps"][0]["recovery_unit_id"] = "unit-1"
        external["steps"][0]["recovery_mode"] = "external"
        external["steps"][0]["journal_classification"] = "external_or_unknown"
        external["recovery_units"] = [
            {
                "unit_id": "unit-1",
                "mode": "external",
                "step_ids": ["external-step"],
                "state": "executing",
            }
        ]
        journal._sync_plan(external_turn, external)
        external_turn.with_user(SUPERUSER_ID).write(
            {
                "capability_plan_payload": {
                    "format_version": 1,
                    "answer": "",
                    "confidence": "high",
                    "human_approved": True,
                    "plan": external,
                }
            }
        )
        journal._mark_turn_failure(external_turn)
        external_row = journal.search([("turn_id", "=", external_turn.id)], limit=1)
        self.assertEqual(external_row.state, "uncertain")

    def test_cleanup_removes_expired_rows(self):
        env = self._env()
        target = env["res.partner"].create({"name": "JOURNAL TTL"})
        turn = self._turn(env, "ttl", target.id)
        prepared = asyncio.run(
            self._plans(env, turn).prepare(
                (
                    PlannedCapability(
                        "odoo.record.patch",
                        {
                            "model": "res.partner",
                            "record_id": target.id,
                            "values": {"name": "TTL PATCH"},
                        },
                        "Actualizar contacto",
                        "ttl-step",
                    ),
                )
            )
        )
        journal = self.env["odoo.ai.effect.journal"].with_user(SUPERUSER_ID)
        journal._sync_plan(turn, prepared)
        row = journal.search([("turn_id", "=", turn.id)], limit=1)
        row.write({"expires_at": fields.Datetime.now() - timedelta(seconds=1)})

        journal._cron_cleanup_effect_journal()

        self.assertFalse(row.exists())
