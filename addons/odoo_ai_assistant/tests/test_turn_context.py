from datetime import UTC, datetime

from odoo import Command
from odoo.tests import TransactionCase, tagged

from ..security import DelegationCodec, DelegationTokenError, QueryDelegationCodec
from ..services import (
    ScreenContextValidationError,
    TurnContextError,
    TurnContextPreparer,
)

NOW = 1_787_337_600
SECRET = b"odoo-test-addon-only-delegation-secret-" + b"s" * 48


@tagged("post_install", "-at_install")
class TestContextTurnPreparation(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company_a = cls.env["res.company"].create({"name": "M2 Company A"})
        cls.company_b = cls.env["res.company"].create({"name": "M2 Company B"})
        cls.outside_company = cls.env["res.company"].create(
            {"name": "M2 Outside Company"}
        )
        cls.user = cls.env["res.users"].create(
            {
                "name": "M2 Limited User",
                "login": "m2-limited-user",
                "company_id": cls.company_a.id,
                "company_ids": [Command.set([cls.company_a.id, cls.company_b.id])],
                "groups_id": [Command.set([cls.env.ref("base.group_user").id])],
            }
        )

    def _user_env(self, company_ids=None):
        return self.env(
            user=self.user.id,
            su=False,
            context={
                **self.env.context,
                "allowed_company_ids": company_ids or [self.company_a.id],
                "lang": "en_US",
            },
        )

    def _screen(self, **overrides):
        values = {
            "view_type": "form",
            "model": "res.partner",
            "res_id": self.company_a.partner_id.id,
            "selected_ids": [self.company_a.partner_id.id],
            "allowed_context_subset": {
                "active_model": "res.partner",
                "active_id": self.company_a.partner_id.id,
            },
            "captured_at": datetime.fromtimestamp(NOW, UTC).isoformat(),
        }
        values.update(overrides)
        return values

    def _codec(self):
        return DelegationCodec(SECRET, clock=lambda: NOW)

    def _query_codec(self):
        return QueryDelegationCodec(SECRET, clock=lambda: NOW)

    def _prepare(self, env, screen=None):
        return TurnContextPreparer(codec=self._codec(), clock=lambda: NOW).prepare(
            env=env,
            screen_payload=screen or self._screen(),
            message="Read the current record",
        )

    def test_effective_user_and_active_companies_are_signed_from_env(self):
        prepared = self._prepare(self._user_env([self.company_a.id, self.company_b.id]))
        claims = self._codec().decode(prepared.delegation_token)

        self.assertEqual(claims.uid, self.user.id)
        self.assertEqual(claims.company_id, self.company_a.id)
        self.assertEqual(
            claims.allowed_company_ids,
            (self.company_a.id, self.company_b.id),
        )
        self.assertEqual(claims.lang, "en_US")
        self.assertEqual(claims.database, self.env.cr.dbname)
        self.assertEqual(claims.model, "res.partner")
        self.assertEqual(claims.record_ids, (self.company_a.partner_id.id,))
        self.assertEqual(claims.expires_at - claims.issued_at, 60)

    def test_browser_identity_is_rejected_before_signing(self):
        for injected in (
            {"uid": self.env.uid},
            {"company_id": self.company_b.id},
            {"allowed_company_ids": [self.company_a.id, self.company_b.id]},
            {"groups": ["base.group_system"]},
            {"display_name": "Trusted from browser"},
        ):
            with (
                self.subTest(injected=injected),
                self.assertRaises(ScreenContextValidationError),
            ):
                self._prepare(self._user_env(), self._screen(**injected))

        clean = self._prepare(self._user_env())
        self.assertEqual(self._codec().decode(clean.delegation_token).uid, self.user.id)

    def test_unauthorized_company_does_not_expand_active_context(self):
        with self.assertRaises(TurnContextError) as failure:
            self._prepare(self._user_env([self.company_a.id, self.outside_company.id]))

        self.assertEqual(failure.exception.code, "identity_unavailable")

    def test_token_is_not_in_browser_payload_or_repr(self):
        prepared = self._prepare(self._user_env())

        self.assertNotIn(prepared.delegation_token, repr(prepared))
        self.assertNotIn(
            prepared.delegation_token,
            repr(prepared.to_browser_payload()),
        )
        self.assertEqual(
            prepared.to_browser_payload(), {"turn_id": str(prepared.turn_id)}
        )

    def test_query_turn_uses_visible_runtime_fields_and_separate_token_family(self):
        from ..services import QueryTurnContextPreparer

        prepared = QueryTurnContextPreparer(
            codec=self._query_codec(), clock=lambda: NOW
        ).prepare(
            env=self._user_env(),
            screen_payload=self._screen(
                res_id=None,
                selected_ids=[],
                allowed_context_subset={"active_model": "res.partner"},
            ),
            message="Count visible contacts",
        )
        claims = self._query_codec().decode(prepared.delegation_token)

        self.assertEqual(claims.uid, self.user.id)
        self.assertEqual(claims.model, "res.partner")
        self.assertIn("id", claims.allowed_fields)
        self.assertIn("display_name", claims.allowed_fields)
        self.assertNotIn("message_ids", claims.allowed_fields)
        self.assertEqual(
            claims.scopes,
            ("query_schema", "query_records", "aggregate_records"),
        )
        self.assertEqual(claims.expires_at - claims.issued_at, 120)
        with self.assertRaises(DelegationTokenError):
            self._codec().decode(prepared.delegation_token)
