from unittest.mock import patch

from odoo import Command
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import TransactionCase, tagged

from ..models.assistant_bridge import SECRET_FILE_PARAM, SERVICE_URL_PARAM
from ..services import AssistantServiceError


def _snapshot(overrides=None, *, revision=3):
    requested = overrides or {
        "source_roots": ["/srv/odoo/addons"],
        "log_provider": "file",
        "reasoning_model": "gpt-5.6-codex",
        "reasoning_startup_timeout_seconds": 20.0,
        "reasoning_turn_timeout_seconds": 180.0,
    }
    return {
        "ok": True,
        "revision": revision,
        "fingerprint": "a" * 64,
        "overrides": requested,
        "authorized": {
            "source_roots": ["/srv/odoo", "/opt/company/odoo-addons"],
            "log_providers": ["file", "journal"],
        },
        "validation_state": "valid",
        "post_action": "hot",
        "snapshot": {
            "schema_version": 1,
            "fingerprint": "b" * 64,
            "values": [
                {
                    "key": "host.database_url",
                    "ownership": "host_only",
                    "provenance": "config",
                    "value_state": "value",
                    "effective_value": "<redacted>",
                    "readonly_reason": "Assistant database credentials remain host-owned.",
                },
                {
                    "key": "knowledge.provider",
                    "ownership": "discovered",
                    "provenance": "runtime",
                    "value_state": "value",
                    "effective_value": "assistant_postgres",
                    "readonly_reason": None,
                },
                {
                    "key": "logs.provider",
                    "ownership": "admin_mutable",
                    "provenance": "explicit_override",
                    "value_state": "value",
                    "effective_value": "file",
                    "readonly_reason": None,
                },
            ],
        },
    }


class FakeConfigClient:
    def __init__(self, snapshot=None, *, validation_error=None, apply_error=None):
        self.snapshot = snapshot or _snapshot()
        self.validation_error = validation_error
        self.apply_error = apply_error
        self.validated = []
        self.applied = []

    def configuration_snapshot(self):
        return self.snapshot

    def configuration_validate(self, payload):
        self.validated.append(payload)
        if self.validation_error:
            raise AssistantServiceError(self.validation_error)
        return {"ok": True, "validation_state": "valid"}

    def configuration_apply(self, payload):
        self.applied.append(payload)
        if self.apply_error:
            raise AssistantServiceError(self.apply_error)
        return self.snapshot


@tagged("post_install", "-at_install")
class TestM7Settings(TransactionCase):
    def setUp(self):
        super().setUp()
        self.parameters = self.env["ir.config_parameter"]
        self.parameters.set_param(SERVICE_URL_PARAM, "http://127.0.0.1:8079")

    def test_non_admin_cannot_read_or_write_settings(self):
        user = self.env["res.users"].create(
            {
                "name": "M7 Non Admin",
                "login": "m7-non-admin",
                "groups_id": [Command.set([self.env.ref("base.group_user").id])],
            }
        )
        model = self.env["res.config.settings"].with_user(user)

        with self.assertRaises(AccessError):
            model.get_values()

        record = self.env["res.config.settings"].create({})
        with self.assertRaises(AccessError):
            record.with_user(user).set_values()

    def test_get_values_never_exposes_credential_reference(self):
        canary = "/host/private/opaque-reference-canary"
        self.parameters.set_param(SECRET_FILE_PARAM, canary)
        settings = self.env["res.config.settings"]
        fake = FakeConfigClient()

        with patch.object(type(settings), "_client_for_url", return_value=fake):
            values = settings.get_values()

        self.assertTrue(values["assistant_machine_credential_configured"])
        self.assertNotIn(canary, repr(values))
        self.assertNotIn("shared_secret", repr(values))

    def test_valid_roundtrip_uses_only_registered_mutable_keys(self):
        fake = FakeConfigClient()
        settings_model = self.env["res.config.settings"]
        with patch.object(type(settings_model), "_client_for_url", return_value=fake):
            loaded = settings_model.get_values()

        record = self.env["res.config.settings"].create(
            {
                "assistant_service_url": "http://127.0.0.1:8079",
                "assistant_source_roots": "/srv/odoo/addons",
                "assistant_log_provider": "journal",
                "assistant_reasoning_model": "gpt-5.6-codex",
                "assistant_reasoning_startup_timeout_seconds": 25,
                "assistant_reasoning_turn_timeout_seconds": 200,
                "assistant_config_revision": loaded["assistant_config_revision"],
                "assistant_host_only_summary": "manipulated-but-ignored",
            }
        )
        with patch.object(type(record), "_client_for_url", return_value=fake):
            record.set_values()

        requested = fake.applied[-1]["overrides"]
        self.assertEqual(
            set(requested),
            {
                "source_roots",
                "log_provider",
                "reasoning_model",
                "reasoning_startup_timeout_seconds",
                "reasoning_turn_timeout_seconds",
            },
        )
        self.assertNotIn("host", repr(requested))
        self.assertEqual(fake.applied[-1]["expected_revision"], 3)
        self.assertEqual(fake.applied[-1]["actor"]["odoo_uid"], self.env.uid)

    def test_invalid_remote_config_does_not_overwrite_local_url(self):
        original = self.parameters._get_param(SERVICE_URL_PARAM)
        fake = FakeConfigClient(validation_error="configuration_invalid")
        record = self.env["res.config.settings"].create(
            {
                "assistant_service_url": "http://127.0.0.1:9080",
                "assistant_source_roots": "/etc",
                "assistant_config_revision": 3,
            }
        )

        with patch.object(type(record), "_client_for_url", return_value=fake):
            with self.assertRaises(ValidationError):
                record.set_values()

        self.assertEqual(self.parameters._get_param(SERVICE_URL_PARAM), original)
        self.assertFalse(fake.applied)

    def test_stale_revision_is_reported_without_silent_retry(self):
        fake = FakeConfigClient(apply_error="configuration_revision_conflict")
        record = self.env["res.config.settings"].create(
            {
                "assistant_service_url": "http://127.0.0.1:8079",
                "assistant_config_revision": 2,
            }
        )

        with self.assertRaises(ValidationError):
            with self.env.cr.savepoint():
                with patch.object(type(record), "_client_for_url", return_value=fake):
                    record.set_values()

        self.assertEqual(fake.applied[-1]["expected_revision"], 2)

    def test_non_loopback_service_url_is_rejected_before_persistence(self):
        original = self.parameters._get_param(SERVICE_URL_PARAM)
        record = self.env["res.config.settings"].create(
            {
                "assistant_service_url": "http://example.com:8079",
                "assistant_config_revision": 3,
            }
        )

        with self.assertRaises(ValidationError):
            record.set_values()

        self.assertEqual(self.parameters._get_param(SERVICE_URL_PARAM), original)

    def test_settings_view_is_system_admin_only_and_contains_no_secret_field(self):
        view = self.env.ref(
            "odoo_ai_assistant.res_config_settings_view_form_odoo_ai_assistant"
        )
        arch = view.arch_db

        self.assertEqual(view.model, "res.config.settings")
        self.assertIn("base.group_system", arch)
        self.assertNotIn("shared_secret", arch)
        self.assertNotIn("SECRET_FILE", arch)
