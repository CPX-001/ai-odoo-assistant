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
    _start_preview,
    import_status,
    inspect_csv,
    start_csv,
)
from odoo.addons.odoo_ai_assistant.runtime.capabilities.registry import (
    discover_capabilities_for_env,
)
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestPhase11DataImportSession(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        internal_group = cls.env.ref("base.group_user")
        cls.user = cls.env["res.users"].create(
            {
                "name": "P11 Import User",
                "login": "p11-import-user",
                "company_id": cls.env.company.id,
                "company_ids": [Command.set([cls.env.company.id])],
                "groups_id": [Command.set([internal_group.id])],
            }
        )
        cls.other_user = cls.env["res.users"].create(
            {
                "name": "P11 Other User",
                "login": "p11-import-other-user",
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

    def _mapping(self, inspection, *fields):
        by_header = {
            header.casefold(): index
            for index, header in enumerate(inspection["headers"])
        }
        return [
            {"column_index": by_header[field.casefold()], "field": field}
            for field in fields
        ]

    def test_csv_import_is_chunked_durable_and_not_replayed(self):
        env, attachment, turn_uuid = self._turn_with_csv(
            b"name,email\nP11 Alpha,p11-alpha@example.test\nP11 Beta,p11-beta@example.test\n",
            request_id="request.p11.import.0001",
        )
        context = CapabilityContext(env=env, turn_id=turn_uuid)
        inspection = inspect_csv(
            context,
            {"attachment_id": attachment.id, "model": "res.partner"},
        )
        mapping = self._mapping(inspection, "name", "email")
        preview = _start_preview(
            context,
            {
                "attachment_id": attachment.id,
                "model": "res.partner",
                "mapping": mapping,
                "chunk_size": 1,
            },
        )
        self.assertEqual(preview.summary["total_rows"], 2)
        self.assertEqual(preview.summary["chunk_size"], 1)

        started = start_csv(
            context,
            {
                "attachment_id": attachment.id,
                "model": "res.partner",
                "mapping": mapping,
                "chunk_size": 1,
            },
        )
        repeated = start_csv(
            context,
            {
                "attachment_id": attachment.id,
                "model": "res.partner",
                "mapping": mapping,
                "chunk_size": 1,
            },
        )
        self.assertEqual(repeated["session_uuid"], started["session_uuid"])

        worker = self.env["odoo.ai.data.import.session"]
        self.assertTrue(worker._cron_process_pending())
        self.assertTrue(worker._cron_process_pending())

        status = import_status(
            context,
            {"session_uuid": started["session_uuid"], "recent_chunks": 8},
        )
        self.assertEqual(status["state"], "completed")
        self.assertEqual(status["imported_rows"], 2)
        self.assertEqual(status["failed_rows"], 0)
        self.assertEqual(status["remaining_rows"], 0)
        self.assertEqual(status["chunk_count"], 2)
        self.assertEqual(len(status["chunks"]), 2)
        self.assertTrue(
            all(chunk["state"] == "completed" for chunk in status["chunks"])
        )
        self.assertEqual(
            env["res.partner"].search_count(
                [("email", "in", ["p11-alpha@example.test", "p11-beta@example.test"])]
            ),
            2,
        )

        self.assertFalse(worker._cron_process_pending())
        self.assertEqual(
            env["res.partner"].search_count(
                [("email", "in", ["p11-alpha@example.test", "p11-beta@example.test"])]
            ),
            2,
        )

    def test_invalid_later_chunk_keeps_prior_receipt_without_corrupting_it(self):
        env, attachment, turn_uuid = self._turn_with_csv(
            b"name,type\nP11 Valid,contact\nP11 Invalid,not_a_partner_type\n",
            request_id="request.p11.import.0002",
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

        status = import_status(
            context,
            {"session_uuid": started["session_uuid"], "recent_chunks": 8},
        )
        self.assertEqual(status["state"], "partial")
        self.assertEqual(status["imported_rows"], 1)
        self.assertEqual(status["failed_rows"], 1)
        self.assertEqual(status["remaining_rows"], 0)
        self.assertEqual(status["chunks"][0]["state"], "completed")
        self.assertEqual(status["chunks"][1]["state"], "rejected")
        self.assertEqual(
            env["res.partner"].search_count([("name", "=", "P11 Valid")]),
            1,
        )
        self.assertEqual(
            env["res.partner"].search_count([("name", "=", "P11 Invalid")]),
            0,
        )
        self.assertFalse(worker._cron_process_pending())
        self.assertEqual(
            env["res.partner"].search_count([("name", "=", "P11 Valid")]),
            1,
        )

    def test_mapping_and_status_authority_fail_closed(self):
        env, attachment, turn_uuid = self._turn_with_csv(
            b"name,company_id\nP11 Boundary,1\n",
            request_id="request.p11.import.0003",
        )
        context = CapabilityContext(env=env, turn_id=turn_uuid)
        inspection = inspect_csv(
            context,
            {"attachment_id": attachment.id, "model": "res.partner"},
        )
        company_index = {
            header: index for index, header in enumerate(inspection["headers"])
        }["company_id"]
        with self.assertRaisesRegex(CapabilityError, "data_import_mapping_invalid"):
            _start_preview(
                context,
                {
                    "attachment_id": attachment.id,
                    "model": "res.partner",
                    "mapping": [
                        {"column_index": 0, "field": "name"},
                        {"column_index": company_index, "field": "company_id"},
                    ],
                },
            )

        started = start_csv(
            context,
            {
                "attachment_id": attachment.id,
                "model": "res.partner",
                "mapping": [{"column_index": 0, "field": "name"}],
            },
        )
        other = CapabilityContext(env=self._env(self.other_user), turn_id=turn_uuid)
        with self.assertRaisesRegex(CapabilityError, "data_import_turn_binding_invalid"):
            import_status(other, {"session_uuid": started["session_uuid"]})

    def test_capability_contract_uses_segmented_policy_bound_effect(self):
        env = self._env()
        registry = discover_capabilities_for_env(env)
        start = registry.resolve("assistant.data_import.start_csv")
        inspect = registry.resolve("assistant.data_import.inspect_csv")
        status = registry.resolve("assistant.data_import.status")

        self.assertEqual(start.effect, CapabilityEffect.INTERNAL_IRREVERSIBLE)
        self.assertEqual(start.exposure, CapabilityExposure.PLAN)
        self.assertEqual(start.audit_metadata["recovery_mode"], "segmented")
        self.assertEqual(start.audit_metadata["journal_classification"], "irreversible")
        self.assertIsNotNone(start.preview_handler)
        self.assertIsNotNone(start.verify_handler)
        self.assertEqual(inspect.effect, CapabilityEffect.READ_ONLY)
        self.assertEqual(status.effect, CapabilityEffect.READ_ONLY)
