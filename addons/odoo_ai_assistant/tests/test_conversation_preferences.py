from datetime import UTC, datetime

from odoo import SUPERUSER_ID, Command
from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase

from ..models.chat_policy import resolve_capability_policy
from ..runtime.capabilities import (
    CapabilityApproval,
    CapabilityContext,
    CapabilityExposure,
    clear_discovery_cache,
    discover_capabilities,
)


class TestAssistantConversationPreferences(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        internal_group = cls.env.ref("base.group_user")
        company = cls.env.company
        cls.user = cls.env["res.users"].create(
            {
                "name": "AI Conversation Preference User",
                "login": "ai-conversation-preference-user",
                "company_id": company.id,
                "company_ids": [Command.set([company.id])],
                "groups_id": [Command.set([internal_group.id])],
            }
        )

    def setUp(self):
        super().setUp()
        clear_discovery_cache()

    def _env(self):
        return self.env(user=self.user, su=False)

    def _conversation(self, title):
        return self._env()["odoo.ai.conversation"].create({"title": title})

    def _screen(self):
        return {
            "action_id": None,
            "allowed_context_subset": {},
            "captured_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "menu_id": None,
            "model": "res.partner",
            "res_id": None,
            "selected_ids": [],
            "view_type": "list",
        }

    def _enqueue(self, conversation, *, message, request_id):
        env = self._env()
        result = env["odoo.ai.turn"].enqueue_for_current_user(
            message=message,
            screen=self._screen(),
            conversation_uuid=conversation.conversation_uuid,
            client_request_id=request_id,
        )
        self.assertTrue(result["ok"])
        return env["odoo.ai.turn"]._owned_turn(result["turn_id"])

    def test_conversation_autonomy_override_is_scoped_and_host_bounded(self):
        env = self._env()
        preference = env["odoo.ai.user.preference"]
        preference.set_current_agent_profile("balanced")
        conversation_a = self._conversation("Autonomy A")
        conversation_b = self._conversation("Autonomy B")

        policy = env["odoo.ai.chat.policy"]
        self.assertIsNone(
            policy.conversation_autonomy_profile(conversation_a.conversation_uuid)
        )
        policy.set_conversation_autonomy_profile(
            conversation_a.conversation_uuid,
            "full_access",
        )

        snapshot_a = policy.policy_layers_for_turn(
            conversation_id=conversation_a.conversation_uuid,
            message="Consulta segura",
        )
        self.assertEqual(
            snapshot_a["layers"]["user"]["confirmation_mode"],
            "protected_only",
        )
        self.assertEqual(snapshot_a["layers"]["user"]["max_auto_risk"], "protected")
        resolved_a = resolve_capability_policy(snapshot_a)
        self.assertEqual(resolved_a["confirmation_mode"], "protected_only")
        self.assertEqual(resolved_a["max_auto_risk"], "protected")

        snapshot_b = policy.policy_layers_for_turn(
            conversation_id=conversation_b.conversation_uuid,
            message="Consulta segura",
        )
        self.assertEqual(snapshot_b["layers"]["user"]["confirmation_mode"], "risk_based")
        self.assertEqual(snapshot_b["layers"]["user"]["max_auto_risk"], "moderate")

        policy.set_conversation_autonomy_profile(
            conversation_a.conversation_uuid,
            None,
        )
        self.assertIsNone(
            policy.conversation_autonomy_profile(conversation_a.conversation_uuid)
        )
        restored = policy.policy_layers_for_turn(
            conversation_id=conversation_a.conversation_uuid,
            message="Consulta segura",
        )
        self.assertEqual(restored["layers"]["user"]["max_auto_risk"], "moderate")

    def test_response_language_is_scoped_and_snapshotted_per_turn(self):
        env = self._env()
        conversation = self._conversation("Language A")
        conversation_model = env["odoo.ai.conversation"]
        conversation_model.set_response_language_preference(
            conversation.conversation_uuid,
            mode="fixed",
            language="es",
        )
        turn_a = self._enqueue(
            conversation,
            message="Primer turno",
            request_id="request.conversation.preference.lang.0001",
        )
        self.assertEqual(turn_a.response_language_mode, "fixed")
        self.assertEqual(turn_a.response_language, "es")

        conversation_model.set_response_language_preference(
            conversation.conversation_uuid,
            mode="fixed",
            language="en",
        )
        turn_a.invalidate_recordset()
        self.assertEqual(turn_a.response_language_mode, "fixed")
        self.assertEqual(turn_a.response_language, "es")

        turn_b = self._enqueue(
            conversation,
            message="Second turn",
            request_id="request.conversation.preference.lang.0002",
        )
        self.assertEqual(turn_b.response_language_mode, "fixed")
        self.assertEqual(turn_b.response_language, "en")

        turn_a.with_user(SUPERUSER_ID).write(
            {"state": "failed", "error_code": "preference_snapshot_fixture"}
        )
        context_b = turn_b.conversation_context_snapshot()
        self.assertEqual(context_b["session_settings"]["response_language_mode"], "fixed")
        self.assertEqual(context_b["session_settings"]["response_language"], "en")
        self.assertEqual(
            context_b["session_settings"]["odoo_user_language"],
            turn_b.lang,
        )

    def test_response_language_validation_rejects_invalid_combinations(self):
        conversation = self._conversation("Language validation")
        model = self._env()["odoo.ai.conversation"]
        with self.assertRaises(ValidationError):
            model.set_response_language_preference(
                conversation.conversation_uuid,
                mode="fixed",
                language="not a language",
            )
        with self.assertRaises(ValidationError):
            model.set_response_language_preference(
                conversation.conversation_uuid,
                mode="automatic",
                language="es",
            )

    def test_preference_capabilities_are_discovered_with_safe_authority(self):
        registry = discover_capabilities()
        read = registry.resolve("assistant.conversation.preferences")
        autonomy = registry.resolve("assistant.conversation.set_autonomy")
        language = registry.resolve("assistant.conversation.set_response_language")

        self.assertEqual(read.exposure, CapabilityExposure.REASONING)
        self.assertEqual(autonomy.exposure, CapabilityExposure.PLAN)
        self.assertEqual(autonomy.approval, CapabilityApproval.ALWAYS)
        self.assertEqual(language.exposure, CapabilityExposure.PLAN)
        self.assertEqual(language.approval, CapabilityApproval.NONE)
        self.assertIsNotNone(autonomy.preview_handler)
        self.assertIsNotNone(autonomy.verify_handler)
        self.assertIsNotNone(language.preview_handler)
        self.assertIsNotNone(language.verify_handler)

    def test_response_language_capability_preview_execute_verify(self):
        env = self._env()
        conversation = self._conversation("Language capability")
        context = CapabilityContext(
            env=env,
            turn_id="conversation-preference-capability-test",
            conversation_id=conversation.conversation_uuid,
            metadata={
                "capability_policy": {
                    "confirmation_mode": "risk_based",
                    "max_auto_risk": "moderate",
                    "allow_synthetic_data": True,
                    "synthetic_data_authorized": False,
                    "max_tool_calls_per_turn": 32,
                    "max_write_steps_per_plan": 12,
                    "max_replans": 2,
                    "max_consecutive_failures": 3,
                }
            },
        )
        definition = discover_capabilities().resolve(
            "assistant.conversation.set_response_language"
        )
        arguments = {"mode": "fixed", "language": "es_ES"}

        preview = definition.preview_handler(context, arguments)
        self.assertEqual(preview.summary["current"]["mode"], "inherit")
        self.assertEqual(preview.summary["requested"]["language"], "es_ES")
        result = definition.handler(context, arguments)
        self.assertEqual(result["mode"], "fixed")
        verification = definition.verify_handler(context, arguments)
        self.assertTrue(verification.verified)
        self.assertEqual(
            env["odoo.ai.conversation"].response_language_preference(
                conversation.conversation_uuid
            ),
            {"mode": "fixed", "language": "es_ES"},
        )
