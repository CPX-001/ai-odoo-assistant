from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestAssistantAdminUiHelp(TransactionCase):
    def test_knowledge_fields_explain_inputs_and_calculated_values(self):
        field_names = (
            "source_uuid",
            "name",
            "filename",
            "mimetype",
            "data",
            "file_size",
            "content_fingerprint",
            "access_mode",
            "enabled",
            "owner_user_id",
            "company_id",
            "conversation_id",
            "version",
            "chunk_count",
            "indexed_at",
            "indexed_fingerprint",
            "error_code",
            "state",
        )
        metadata = self.env["odoo.ai.knowledge.source"].fields_get(
            field_names,
            attributes=["help", "string"],
        )

        self.assertEqual(set(metadata), set(field_names))
        for field_name in field_names:
            self.assertTrue(metadata[field_name]["string"])
            self.assertTrue(metadata[field_name]["help"], field_name)

    def test_diagnostics_fields_are_read_only_and_explained(self):
        field_names = (
            "readiness",
            "scheduler_capacity",
            "scheduler_queue",
            "scheduler_wait",
            "diagnostic_errors",
            "diagnostic_warnings",
            "diagnostic_ok",
            "codex_account_state",
            "codex_account_identity",
            "codex_account_plan",
            "codex_account_detail",
            "codex_account_usage",
        )
        metadata = self.env["odoo.ai.assistant.diagnostics"].fields_get(
            field_names,
            attributes=["help", "readonly", "string"],
        )

        self.assertEqual(set(metadata), set(field_names))
        for field_name in field_names:
            self.assertTrue(metadata[field_name]["readonly"], field_name)
            self.assertTrue(metadata[field_name]["string"])
            self.assertTrue(metadata[field_name]["help"], field_name)

    def test_forms_include_visible_customer_guidance(self):
        knowledge_arch = self.env.ref(
            "odoo_ai_assistant.view_odoo_ai_knowledge_source_form"
        ).arch_db
        diagnostics_arch = self.env.ref(
            "odoo_ai_assistant.view_odoo_ai_assistant_diagnostics_form"
        ).arch_db

        self.assertIn("Add a supported text document", knowledge_arch)
        self.assertIn("Use a title your team will recognize", knowledge_arch)
        self.assertIn("This page is read-only", diagnostics_arch)
        self.assertIn("No action is required", diagnostics_arch)
