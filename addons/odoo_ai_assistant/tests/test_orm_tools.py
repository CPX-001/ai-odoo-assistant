from contextlib import contextmanager
from datetime import UTC, datetime
from uuid import UUID

from odoo import Command
from odoo.tests import TransactionCase, tagged

from ..security import DelegationCodec, DelegationPayload
from ..services.orm_tools import DelegatedOrmToolExecutor, OrmToolError

NOW = 1_787_337_600
SECRET = b"odoo-m2-03-delegation-secret-" + b"s" * 48
TURN_ID = UUID("12345678-1234-5678-1234-567812345678")


@tagged("post_install", "-at_install")
class TestDelegatedOrmTools(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.allowed_country = cls.env["res.country"].create(
            {"name": "M2 Allowed Country", "code": "XA"}
        )
        cls.denied_country = cls.env["res.country"].create(
            {"name": "M2 Denied Country", "code": "XD"}
        )
        cls.restricted_group = cls.env["res.groups"].create(
            {"name": "M2 restricted country reader"}
        )
        cls.env["ir.rule"].create(
            {
                "name": "M2 delegated country rule",
                "model_id": cls.env["ir.model"]._get_id("res.country"),
                "domain_force": f"[('id', '=', {cls.allowed_country.id})]",
                "groups": [Command.link(cls.restricted_group.id)],
                "perm_read": True,
                "perm_write": False,
                "perm_create": False,
                "perm_unlink": False,
            }
        )
        cls.user = cls.env["res.users"].create(
            {
                "name": "M2 ORM Limited User",
                "login": "m2-orm-limited-user",
                "company_id": cls.env.company.id,
                "company_ids": [Command.set([cls.env.company.id])],
                "groups_id": [
                    Command.set(
                        [
                            cls.env.ref("base.group_user").id,
                            cls.restricted_group.id,
                        ]
                    )
                ],
            }
        )

    def _codec(self, now=NOW):
        return DelegationCodec(SECRET, clock=lambda: now)

    def _token(
        self,
        *,
        model="res.country",
        record_ids=None,
        scopes=("fields_get", "read_records"),
        expires_at=NOW + 60,
        max_records=1,
        max_fields=32,
    ):
        ids = record_ids or (self.allowed_country.id,)
        payload = DelegationPayload(
            format_version=1,
            jti="jti_0123456789abcdefghij",
            turn_id=TURN_ID,
            database=self.env.cr.dbname,
            uid=self.user.id,
            company_id=self.env.company.id,
            allowed_company_ids=(self.env.company.id,),
            lang="en_US",
            model=model,
            record_ids=tuple(ids),
            scopes=scopes,
            issued_at=NOW,
            expires_at=expires_at,
            max_records=max_records,
            max_fields=max_fields,
        )
        return self._codec().encode(payload)

    @contextmanager
    def _environment(self, claims):
        delegated = self.env(
            user=claims.uid,
            su=False,
            context={
                **self.env.context,
                "allowed_company_ids": list(claims.allowed_company_ids),
                "lang": claims.lang,
            },
        )
        self.assertFalse(delegated.su)
        self.assertEqual(delegated.uid, self.user.id)
        yield delegated

    def _executor(self, *, now=NOW):
        return DelegatedOrmToolExecutor(
            codec=self._codec(now),
            environment_provider=self._environment,
            observed_at=lambda: datetime.fromtimestamp(NOW, UTC),
        )

    def test_exact_scoped_record_is_read_as_the_delegated_user(self):
        result = self._executor().read_records(
            delegation_token=self._token(),
            turn_id=str(TURN_ID),
            model="res.country",
            record_ids=[self.allowed_country.id],
            fields=["display_name", "code"],
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["model"], "res.country")
        self.assertEqual(result["records"][0]["id"], self.allowed_country.id)
        self.assertEqual(result["records"][0]["fields"]["code"], "XA")

    def test_record_rule_denial_is_not_bypassed(self):
        token = self._token(record_ids=(self.denied_country.id,))

        with self.assertRaises(OrmToolError) as failure:
            self._executor().read_records(
                delegation_token=token,
                turn_id=str(TURN_ID),
                model="res.country",
                record_ids=[self.denied_country.id],
                fields=["name"],
            )

        self.assertIn(failure.exception.code, {"access_denied", "delegation_rejected"})

    def test_model_id_and_scope_cannot_be_expanded(self):
        executor = self._executor()
        token = self._token(scopes=("read_records",))

        attempts = (
            {"model": "res.partner", "record_ids": [self.allowed_country.id]},
            {"model": "res.country", "record_ids": [self.denied_country.id]},
        )
        for values in attempts:
            with self.assertRaises(OrmToolError) as failure:
                executor.read_records(
                    delegation_token=token,
                    turn_id=str(TURN_ID),
                    fields=["name"],
                    **values,
                )
            self.assertEqual(failure.exception.code, "scope_denied")

        with self.assertRaises(OrmToolError) as wrong_scope:
            executor.get_model_metadata(
                delegation_token=token,
                turn_id=str(TURN_ID),
                model="res.country",
            )
        self.assertEqual(wrong_scope.exception.code, "scope_denied")

    def test_tampered_and_expired_delegations_are_rejected(self):
        token = self._token()
        replacement = "A" if token[-1] != "A" else "B"
        with self.assertRaises(OrmToolError) as tampered:
            self._executor().read_records(
                delegation_token=token[:-1] + replacement,
                turn_id=str(TURN_ID),
                model="res.country",
                record_ids=[self.allowed_country.id],
                fields=["name"],
            )
        self.assertEqual(tampered.exception.code, "delegation_rejected")

        with self.assertRaises(OrmToolError) as expired:
            self._executor(now=NOW + 60).read_records(
                delegation_token=token,
                turn_id=str(TURN_ID),
                model="res.country",
                record_ids=[self.allowed_country.id],
                fields=["name"],
            )
        self.assertEqual(expired.exception.code, "delegation_rejected")

    def test_unknown_and_excess_fields_are_controlled(self):
        with self.assertRaises(OrmToolError) as unknown:
            self._executor().read_records(
                delegation_token=self._token(),
                turn_id=str(TURN_ID),
                model="res.country",
                record_ids=[self.allowed_country.id],
                fields=["does_not_exist"],
            )
        self.assertEqual(unknown.exception.code, "invalid_fields")

        with self.assertRaises(OrmToolError) as excess:
            self._executor().read_records(
                delegation_token=self._token(max_fields=1),
                turn_id=str(TURN_ID),
                model="res.country",
                record_ids=[self.allowed_country.id],
                fields=["name", "code"],
            )
        self.assertEqual(excess.exception.code, "limit_exceeded")

    def test_metadata_is_bounded_and_filters_inaccessible_fields(self):
        token = self._token(model="res.users", record_ids=(self.user.id,))
        result = self._executor().get_model_metadata(
            delegation_token=token,
            turn_id=str(TURN_ID),
            model="res.users",
        )

        self.assertTrue(result["ok"])
        self.assertLessEqual(len(result["fields"]), 32)
        self.assertNotIn("request", result["fields"])
        self.assertIn("display_name", result["fields"])

    def test_response_bytes_are_bounded(self):
        partner = self.env["res.partner"].create(
            {"name": "M2 large value", "comment": "x" * 40_000}
        )
        token = self._token(model="res.partner", record_ids=(partner.id,))

        with self.assertRaises(OrmToolError) as failure:
            self._executor().read_records(
                delegation_token=token,
                turn_id=str(TURN_ID),
                model="res.partner",
                record_ids=[partner.id],
                fields=["comment"],
            )
        self.assertEqual(failure.exception.code, "response_too_large")
