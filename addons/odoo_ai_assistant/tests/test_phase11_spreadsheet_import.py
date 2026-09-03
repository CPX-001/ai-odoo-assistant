from __future__ import annotations

import base64
from datetime import UTC, datetime
from io import BytesIO

from openpyxl import Workbook

from odoo import Command
from odoo.addons.odoo_ai_assistant.runtime.capabilities.contracts import CapabilityContext
from odoo.addons.odoo_ai_assistant.runtime.capabilities.providers.assistant_data_import import (
    import_status,
)
from odoo.addons.odoo_ai_assistant.runtime.capabilities.providers.assistant_data_import_tabular import (
    inspect_file,
    start_file,
)
from odoo.addons.odoo_ai_assistant.runtime.capabilities.registry import (
    discover_capabilities_for_env,
)
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestPhase11SpreadsheetImport(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        internal = cls.env.ref("base.group_user")
        partner_manager = cls.env.ref("base.group_partner_manager")
        cls.user = cls.env["res.users"].create(
            {
                "name": "P11 Spreadsheet Import User",
                "login": "p11-spreadsheet-import-user",
                "company_id": cls.env.company.id,
                "company_ids": [Command.set([cls.env.company.id])],
                "groups_id": [Command.set([internal.id, partner_manager.id])],
            }
        )

    def _env(self):
        return self.env(user=self.user, su=False)

    def _xlsx(self):
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Contacts"
        sheet.append(["name", "email"])
        sheet.append(["P11 Excel Alpha", "p11-excel-alpha@example.test"])
        sheet.append(["P11 Excel Beta", "p11-excel-beta@example.test"])
        stream = BytesIO()
        workbook.save(stream)
        return stream.getvalue()

    def _turn_with_xlsx(self, *, request_id):
        env = self._env()
        attachment = env["odoo.ai.knowledge.attachment"].create_upload(
            filename="contacts.xlsx",
            mimetype="application/octet-stream",
            data=base64.b64encode(self._xlsx()),
        )
        result = env["odoo.ai.turn"].enqueue_for_current_user(
            message=(
                "Import this Excel workbook into contacts."
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

    def test_xlsx_attachment_reaches_generic_import_capabilities(self):
        env, attachment, turn_uuid = self._turn_with_xlsx(
            request_id="request.p11.xlsx.0001"
        )
        self.assertEqual(
            attachment.mimetype,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        self.assertTrue(attachment.filename.endswith(".xlsx"))
        self.assertGreater(attachment.file_size, 0)

        context = CapabilityContext(env=env, turn_id=turn_uuid)
        registry = discover_capabilities_for_env(env)
        available = {item.name for item in registry.available(context)}
        self.assertIn("assistant.data_import.inspect_file", available)
        self.assertIn("assistant.data_import.start_file", available)

        inspection = inspect_file(
            context,
            {"attachment_id": attachment.id, "model": "res.partner"},
        )
        self.assertEqual(inspection["headers"], ["name", "email"])
        self.assertEqual(inspection["estimated_rows"], 2)
        by_header = {
            header.casefold(): index
            for index, header in enumerate(inspection["headers"])
        }
        mapping = [
            {"column_index": by_header["name"], "field": "name"},
            {"column_index": by_header["email"], "field": "email"},
        ]
        started = start_file(
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
        self.assertEqual(status["state"], "completed")
        self.assertEqual(status["imported_rows"], 2)
        self.assertEqual(status["failed_rows"], 0)
        self.assertEqual(status["chunk_count"], 2)
        self.assertEqual(
            env["res.partner"].search_count(
                [
                    (
                        "email",
                        "in",
                        [
                            "p11-excel-alpha@example.test",
                            "p11-excel-beta@example.test",
                        ],
                    )
                ]
            ),
            2,
        )

    def test_spreadsheet_upload_does_not_turn_into_knowledge_document(self):
        env = self._env()
        attachment = env["odoo.ai.knowledge.attachment"].create_upload(
            filename="contacts.xlsx",
            mimetype=(
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            ),
            data=base64.b64encode(self._xlsx()),
        )
        self.assertFalse(attachment.knowledge_source_id)
        self.assertIn("structured import", attachment.extracted_text)
