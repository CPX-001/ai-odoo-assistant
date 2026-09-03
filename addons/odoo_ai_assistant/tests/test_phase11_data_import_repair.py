from __future__ import annotations

import base64
from datetime import UTC, datetime

from odoo import Command
from odoo.addons.odoo_ai_assistant.runtime.capabilities.contracts import (
    CapabilityContext,
    CapabilityEffect,
    CapabilityError,
    CapabilityExposure,
)
from odoo.addons.odoo_ai_assistant.runtime.capabilities.providers.assistant_data_import import (
    import_status,
    inspect_csv,
    start_csv,
)
from odoo.addons.odoo_ai_assistant.runtime.capabilities.providers.assistant_data_import_repair import (
    _repair_preview,
    inspect_cleanup,
    inspect_rejected,
    resume_csv,
    start_clean_csv,
)
from odoo.addons.odoo_ai_assistant.runtime.capabilities.registry import (
    discover_capabilities_for_env,
)
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestPhase11DataImportCleanupRepair(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        internal_group = cls.env.ref("base.group_user")
        cls.user = cls.env["res.users"].create(
            {
                "name": "P11 Repair User",
                "login": "p11-repair-user",
                "company_id": cls.env.company.id,
                "company_ids": [Command.set([cls.env.company.id])],
                "groups_id": [Command.set([internal_group.id])],
            }
        )
        cls.other_user = cls.env["res.users"].create(
            {
                "name": "P11 Repair Other User",
                "login": "p11-repair-other-user",
                "company_id": cls.env.company.id,
                "company_ids": [Command.set([cls.env.company.id])],
                "groups_id": [Command.set([internal_group.id])],
            }
        )

    def _env(self, user=None):
        return self.env(user=user or self.user, su=False)

    def _turn_with_csv(self, payload: bytes, *, request_id: str):
        env = self._env()
        attachment = env["odoo.ai.knowledge.attachment"].create_upload(
            filename="contacts.csv",
            mimetype="text/csv",
            data=base64.b64encode(payload),
        )
        result = env["odoo.ai.turn"].enqueue_for_current_user(
            message=(
                "Import this CSV into contacts."
                f"\n[[odoo_ai_attachment:{attachment.token}]]"
            ),
            screen={
                "action_id": None,
                "allowed_context_subset": {},
                "captured_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                "menu_id": None,
                "model": "res.partner",
                "res_id": None,
                "selected_ids": [],
                "view_type": "list",
            },
            client_request_id=request_id,
        )
        return env, attachment, result["turn_id"]

    @staticmethod
    def _mapping(inspection, *fields):
        by_header = {
            header.casefold(): index
            for index, header in enumerate(inspection["headers"])
        }
        return [
            {"column_index": by_header[field.casefold()], "field": field}
            for field in fields
        ]

    def test_deterministic_cleanup_is_previewed_and_counted_only_after_commit(self):
        env, attachment, turn_uuid = self._turn_with_csv(
            b"name,email\n  P11   Clean  ,\n",
            request_id="request.p11.cleanup.0001",
        )
        context = CapabilityContext(env=env, turn_id=turn_uuid)
        inspection = inspect_csv(
            context,
            {"attachment_id": attachment.id, "model": "res.partner"},
        )
        mapping = self._mapping(inspection, "name", "email")
        arguments = {
            "attachment_id": attachment.id,
            "model": "res.partner",
            "mapping": mapping,
            "cleanup_rules": [
                {"field": "name", "operation": "normalize_whitespace"},
                {
                    "field": "email",
                    "operation": "set_if_empty",
                    "value": "p11-clean@example.test",
                },
            ],
            "chunk_size": 1,
        }
        preview = inspect_cleanup(context, arguments)
        self.assertEqual(preview["planned_corrected_rows"], 1)
        self.assertEqual(preview["duplicate_rows_before"], 0)
        self.assertEqual(preview["duplicate_rows_after"], 0)
        self.assertTrue(preview["samples"])

        started = start_clean_csv(context, arguments)
        queued = import_status(context, {"session_uuid": started["session_uuid"]})
        self.assertEqual(queued["corrected_rows"], 0)

        self.assertTrue(self.env["odoo.ai.data.import.session"]._cron_process_pending())
        status = import_status(context, {"session_uuid": started["session_uuid"]})
        self.assertEqual(status["state"], "completed")
        self.assertEqual(status["imported_rows"], 1)
        self.assertEqual(status["corrected_rows"], 1)
        partner = env["res.partner"].search(
            [("email", "=", "p11-clean@example.test")],
            limit=1,
        )
        self.assertEqual(partner.name, "P11 Clean")

    def test_cleanup_cannot_widen_mapping_or_field_authority(self):
        env, attachment, turn_uuid = self._turn_with_csv(
            b"name,company_id\nP11 Boundary,1\n",
            request_id="request.p11.cleanup.0002",
        )
        context = CapabilityContext(env=env, turn_id=turn_uuid)
        inspection = inspect_csv(
            context,
            {"attachment_id": attachment.id, "model": "res.partner"},
        )
        mapping = self._mapping(inspection, "name")
        with self.assertRaisesRegex(CapabilityError, "data_import_cleanup_invalid"):
            inspect_cleanup(
                context,
                {
                    "attachment_id": attachment.id,
                    "model": "res.partner",
                    "mapping": mapping,
                    "cleanup_rules": [
                        {
                            "field": "company_id",
                            "operation": "replace_exact",
                            "match": "1",
                            "value": "2",
                        }
                    ],
                },
            )

    def test_rejected_chunk_can_be_repaired_and_resumed_without_replay(self):
        env, attachment, turn_uuid = self._turn_with_csv(
            b"name,type\nP11 Repair Valid,contact\nP11 Repair Invalid,not_a_partner_type\n",
            request_id="request.p11.repair.0003",
        )
        context = CapabilityContext(env=env, turn_id=turn_uuid)
        inspection = inspect_csv(
            context,
            {"attachment_id": attachment.id, "model": "res.partner"},
        )
        mapping = self._mapping(inspection, "name", "type")
        started = start_csv(
            context,
            {
                "attachment_id": attachment.id,
                "model": "res.partner",
                "mapping": mapping,
                "chunk_size": 1,
            },
        )
        worker = self.env["odoo.ai.data.import.session"]
        self.assertTrue(worker._cron_process_pending())
        self.assertTrue(worker._cron_process_pending())

        partial = import_status(context, {"session_uuid": started["session_uuid"]})
        self.assertEqual(partial["state"], "partial")
        self.assertEqual(partial["imported_rows"], 1)
        self.assertEqual(partial["failed_rows"], 1)
        rejected = inspect_rejected(
            context,
            {"session_uuid": started["session_uuid"], "max_rows": 8},
        )
        self.assertEqual(rejected["row_start"], 2)
        self.assertEqual(rejected["row_end"], 2)
        self.assertEqual(rejected["rows"][0]["values"]["type"], "not_a_partner_type")

        repair_arguments = {
            "session_uuid": started["session_uuid"],
            "corrections": [{"row": 2, "field": "type", "value": "contact"}],
        }
        preview = _repair_preview(context, repair_arguments)
        self.assertEqual(preview.summary["rejected_sequence"], 2)
        self.assertEqual(preview.summary["repair_revision"], 1)
        self.assertEqual(preview.summary["planned_chunk_count"], 3)
        resumed = resume_csv(context, repair_arguments)
        self.assertEqual(resumed["state"], "queued")
        self.assertEqual(resumed["planned_chunk_count"], 3)

        self.assertTrue(worker._cron_process_pending())
        status = import_status(
            context,
            {"session_uuid": started["session_uuid"], "recent_chunks": 8},
        )
        self.assertEqual(status["state"], "completed")
        self.assertEqual(status["imported_rows"], 2)
        self.assertEqual(status["failed_rows"], 0)
        self.assertEqual(status["corrected_rows"], 1)
        self.assertEqual(status["remaining_rows"], 0)
        self.assertEqual(status["chunk_count"], 3)
        self.assertEqual(status["planned_chunk_count"], 3)
        self.assertEqual(
            [chunk["state"] for chunk in status["chunks"]],
            ["completed", "rejected", "completed"],
        )
        self.assertEqual(
            env["res.partner"].search_count(
                [("name", "in", ["P11 Repair Valid", "P11 Repair Invalid"])]
            ),
            2,
        )
        self.assertFalse(worker._cron_process_pending())
        self.assertEqual(
            env["res.partner"].search_count(
                [("name", "in", ["P11 Repair Valid", "P11 Repair Invalid"])]
            ),
            2,
        )

    def test_repair_capabilities_remain_plan_bound_and_owner_scoped(self):
        env, attachment, turn_uuid = self._turn_with_csv(
            b"name,type\nP11 Owner,not_a_partner_type\n",
            request_id="request.p11.repair.0004",
        )
        context = CapabilityContext(env=env, turn_id=turn_uuid)
        inspection = inspect_csv(
            context,
            {"attachment_id": attachment.id, "model": "res.partner"},
        )
        mapping = self._mapping(inspection, "name", "type")
        started = start_csv(
            context,
            {
                "attachment_id": attachment.id,
                "model": "res.partner",
                "mapping": mapping,
                "chunk_size": 1,
            },
        )
        self.assertTrue(self.env["odoo.ai.data.import.session"]._cron_process_pending())

        other_context = CapabilityContext(env=self._env(self.other_user), turn_id=turn_uuid)
        with self.assertRaisesRegex(CapabilityError, "data_import_turn_binding_invalid"):
            inspect_rejected(
                other_context,
                {"session_uuid": started["session_uuid"]},
            )

        registry = discover_capabilities_for_env(env)
        cleanup = registry.resolve("assistant.data_import.start_clean_csv")
        resume = registry.resolve("assistant.data_import.resume_csv")
        cleanup_read = registry.resolve("assistant.data_import.inspect_cleanup")
        rejected_read = registry.resolve("assistant.data_import.inspect_rejected")
        self.assertEqual(cleanup.effect, CapabilityEffect.INTERNAL_IRREVERSIBLE)
        self.assertEqual(cleanup.exposure, CapabilityExposure.PLAN)
        self.assertEqual(cleanup.audit_metadata["recovery_mode"], "segmented")
        self.assertEqual(resume.effect, CapabilityEffect.INTERNAL_IRREVERSIBLE)
        self.assertEqual(resume.exposure, CapabilityExposure.PLAN)
        self.assertEqual(resume.audit_metadata["recovery_mode"], "segmented")
        self.assertIsNotNone(cleanup.preview_handler)
        self.assertIsNotNone(cleanup.verify_handler)
        self.assertIsNotNone(resume.preview_handler)
        self.assertIsNotNone(resume.verify_handler)
        self.assertEqual(cleanup_read.effect, CapabilityEffect.READ_ONLY)
        self.assertEqual(rejected_read.effect, CapabilityEffect.READ_ONLY)
