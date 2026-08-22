import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from odoo import Command
from odoo.tests import TransactionCase, tagged

from ..security import DelegationCodec
from ..services import AssistantServiceError, prepare_context_turn

SECRET = b"m2-bridge-delegation-secret-" + b"s" * 48


class FakeContextReadClient:
    def __init__(self):
        self.payload = None

    def context_read(self, payload):
        self.payload = payload
        screen = payload["screen"]
        return {
            "completed_at": datetime.now(UTC).isoformat(),
            "evidence": {},
            "fields_read": ["display_name", "name", "state", "company_id"],
            "instance_id": None,
            "instance_state": "unknown",
            "message": "El registro actual se ha releído con permisos efectivos.",
            "record": {
                "captured_at": datetime.now(UTC).isoformat(),
                "fields": {
                    "display_name": "Bridge Partner",
                    "name": "Bridge Partner",
                    "state": False,
                    "company_id": False,
                },
                "provenance": {"provider": "test"},
                "record": {
                    "display_name": "Bridge Partner",
                    "id": screen["res_id"],
                    "model": screen["model"],
                },
            },
            "status": "ok",
            "turn_id": payload["turn_id"],
        }

    def explain(self, payload):
        self.payload = payload
        screen = payload["screen"]
        return {
            "answer_markdown": "El source comprobado explica la tarea.",
            "citations": [
                {
                    "captured_at": datetime.now(UTC).isoformat(),
                    "display_name": "Bridge Partner",
                    "evidence_id": "11111111-1111-4111-8111-111111111111",
                    "id": screen["res_id"],
                    "kind": "record",
                    "model": screen["model"],
                },
                {
                    "end_line": 12,
                    "evidence_id": "22222222-2222-4222-8222-222222222222",
                    "fingerprint": "sha256:" + "a" * 64,
                    "kind": "source",
                    "logical_path": "fixture/models/res_partner.py",
                    "module": "fixture",
                    "provenance": "third_party_or_custom",
                    "start_line": 8,
                },
            ],
            "completed_at": datetime.now(UTC).isoformat(),
            "confidence": "high",
            "limitations": [],
            "status": "ok",
            "turn_id": payload["turn_id"],
            "workflow": "EXPLAIN",
        }


@tagged("post_install", "-at_install")
class TestAssistantBridge(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = cls.env["res.users"].create(
            {
                "name": "M2 Bridge User",
                "login": "m2-bridge-user",
                "company_id": cls.env.company.id,
                "company_ids": [Command.set([cls.env.company.id])],
                "groups_id": [Command.set([cls.env.ref("base.group_user").id])],
            }
        )
        handle, path = tempfile.mkstemp(prefix="odoo-ai-m2-delegation-")
        os.close(handle)
        cls.secret_path = Path(path)
        cls.secret_path.write_bytes(SECRET)
        cls.secret_path.chmod(0o640)
        cls.addClassCleanup(cls.secret_path.unlink, missing_ok=True)

    def _screen(self):
        return {
            "action_id": 42,
            "menu_id": 7,
            "view_type": "form",
            "model": "res.partner",
            "res_id": self.user.partner_id.id,
            "selected_ids": [self.user.partner_id.id],
            "allowed_context_subset": {
                "active_id": self.user.partner_id.id,
                "active_ids": [self.user.partner_id.id],
                "active_model": "res.partner",
            },
            "captured_at": datetime.now(UTC).isoformat(),
        }

    def test_bridge_signs_real_user_identity_and_returns_no_authority(self):
        client = FakeContextReadClient()
        user_env = self.env(
            user=self.user.id,
            su=False,
            context={
                **self.env.context,
                "allowed_company_ids": [self.env.company.id],
                "lang": "en_US",
            },
        )
        bridge = user_env["odoo.ai.assistant.bridge"]
        direct_prepared = prepare_context_turn(
            env=user_env,
            screen_payload=self._screen(),
            message="¿Qué estado tiene?",
            secret_file=str(self.secret_path),
        )
        self.assertEqual(direct_prepared.user.uid, self.user.id)
        with (
            patch.dict(
                os.environ,
                {"ODOO_AI_DELEGATION_SECRET_FILE": str(self.secret_path)},
            ),
            patch.object(type(bridge), "_client", return_value=client),
        ):
            result = bridge.submit_context_read("¿Qué estado tiene?", self._screen())

        self.assertTrue(result.get("ok"), result)
        self.assertIsNotNone(client.payload)
        claims = DelegationCodec(SECRET).decode(client.payload["delegation_token"])
        self.assertEqual(claims.uid, self.user.id)
        self.assertEqual(claims.company_id, self.env.company.id)
        self.assertEqual(claims.record_ids, (self.user.partner_id.id,))
        self.assertTrue(result["ok"])
        self.assertEqual(result["context"]["model"], "res.partner")
        serialized = repr(result)
        self.assertNotIn(client.payload["delegation_token"], serialized)
        self.assertNotIn("uid", serialized)
        self.assertNotIn("allowed_company_ids", serialized)

    def test_service_error_is_reduced_to_a_stable_browser_code(self):
        bridge = self.env(user=self.user.id, su=False)["odoo.ai.assistant.bridge"]
        with (
            patch.dict(
                os.environ,
                {"ODOO_AI_DELEGATION_SECRET_FILE": str(self.secret_path)},
            ),
            patch.object(
                type(bridge),
                "_client",
                side_effect=AssistantServiceError("authentication_rejected"),
            ),
        ):
            result = bridge.submit_context_read("question", self._screen())

        self.assertEqual(
            result,
            {"error": {"code": "authentication_failed"}, "ok": False},
        )

    def test_explain_derives_identity_and_returns_only_renderable_fields(self):
        client = FakeContextReadClient()
        user_env = self.env(
            user=self.user.id,
            su=False,
            context={
                **self.env.context,
                "allowed_company_ids": [self.env.company.id],
                "lang": "en_US",
            },
        )
        bridge = user_env["odoo.ai.assistant.bridge"]
        with (
            patch.dict(
                os.environ,
                {"ODOO_AI_DELEGATION_SECRET_FILE": str(self.secret_path)},
            ),
            patch.object(type(bridge), "_client", return_value=client),
        ):
            result = bridge.submit_explain("¿Por qué?", self._screen())

        self.assertTrue(result.get("ok"), result)
        self.assertEqual(
            set(result),
            {"answer", "citations", "confidence", "limitations", "ok", "turn_id"},
        )
        self.assertEqual(result["citations"][0]["kind"], "record")
        self.assertEqual(result["citations"][1]["kind"], "source")
        serialized = repr(result)
        self.assertNotIn(client.payload["delegation_token"], serialized)
        self.assertNotIn("allowed_company_ids", serialized)

    def test_explain_rejects_a_citation_for_a_different_current_record(self):
        client = FakeContextReadClient()
        valid_explain = client.explain

        def manipulated(payload):
            response = valid_explain(payload)
            response["citations"][0]["id"] += 1
            return response

        client.explain = manipulated
        bridge = self.env(user=self.user.id, su=False)["odoo.ai.assistant.bridge"]
        with (
            patch.dict(
                os.environ,
                {"ODOO_AI_DELEGATION_SECRET_FILE": str(self.secret_path)},
            ),
            patch.object(type(bridge), "_client", return_value=client),
        ):
            result = bridge.submit_explain("¿Por qué?", self._screen())

        self.assertEqual(
            result,
            {"error": {"code": "invalid_response"}, "ok": False},
        )
