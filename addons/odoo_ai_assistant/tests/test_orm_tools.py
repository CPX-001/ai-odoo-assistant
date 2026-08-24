from contextlib import contextmanager
from datetime import UTC, datetime
from uuid import UUID

from odoo import Command
from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, tagged

from ..security import DelegationCodec, DelegationPayload
from ..services.orm_tools import (
    DelegatedOrmToolExecutor,
    OrmToolError,
    collect_model_metadata,
)

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
        cls.company_b = cls.env["res.company"].create({"name": "M2 ORM Company B"})
        cls.company_b_partner = cls.env["res.partner"].create(
            {"company_id": cls.company_b.id, "name": "M2 Company B Partner"}
        )
        cls.admin_parameter = cls.env["ir.config_parameter"].create(
            {"key": "odoo_ai_assistant.m2_acl_probe", "value": "restricted"}
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

    def test_one_oversized_dynamic_selection_does_not_hide_the_model_schema(self):
        metadata = collect_model_metadata(
            self.env,
            model="res.partner",
            max_fields=64,
            observed_at=datetime.now(UTC),
        )

        self.assertEqual(metadata["model"], "res.partner")
        self.assertIn("name", metadata["fields"])
        self.assertNotIn("tz", metadata["fields"])

    def _token(
        self,
        *,
        model="res.country",
        record_ids=None,
        scopes=("fields_get", "read_records"),
        expires_at=NOW + 60,
        max_records=1,
        max_fields=32,
        jti="jti_0123456789abcdefghij",
        company_id=None,
        allowed_company_ids=None,
        database=None,
        turn_id=TURN_ID,
    ):
        ids = record_ids or (self.allowed_country.id,)
        payload = DelegationPayload(
            format_version=1,
            jti=jti,
            turn_id=turn_id,
            database=database or self.env.cr.dbname,
            uid=self.user.id,
            company_id=company_id or self.env.company.id,
            allowed_company_ids=allowed_company_ids or (self.env.company.id,),
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
        if claims.database != self.env.cr.dbname:
            raise OrmToolError("delegation_rejected", 403)
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
        try:
            if (
                delegated.company.id != claims.company_id
                or tuple(delegated.companies.ids) != claims.allowed_company_ids
            ):
                raise OrmToolError("delegation_rejected", 403)
        except AccessError:
            raise OrmToolError("delegation_rejected", 403) from None
        yield delegated

    def _executor(self, *, now=NOW):
        consumed = set()

        def replay_guard(claims, scope):
            key = (claims.jti, scope)
            if key in consumed:
                raise OrmToolError("delegation_replayed", 403)
            consumed.add(key)

        return DelegatedOrmToolExecutor(
            codec=self._codec(now),
            environment_provider=self._environment,
            replay_guard=replay_guard,
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

    def test_acl_denial_and_missing_record_share_the_same_sanitized_error(self):
        executor = self._executor()
        acl_token = self._token(
            model="ir.config_parameter",
            record_ids=(self.admin_parameter.id,),
            jti="acl_0123456789abcdefghij",
        )
        with self.assertRaises(OrmToolError) as acl_failure:
            executor.read_records(
                delegation_token=acl_token,
                turn_id=str(TURN_ID),
                model="ir.config_parameter",
                record_ids=[self.admin_parameter.id],
                fields=["key"],
            )

        missing_token = self._token(
            record_ids=(2_147_483_647,),
            jti="missing_123456789abcdefghij",
        )
        with self.assertRaises(OrmToolError) as missing_failure:
            executor.read_records(
                delegation_token=missing_token,
                turn_id=str(TURN_ID),
                model="res.country",
                record_ids=[2_147_483_647],
                fields=["name"],
            )

        self.assertEqual(acl_failure.exception.code, "access_denied")
        self.assertEqual(missing_failure.exception.code, "access_denied")

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

    def test_wrong_turn_database_and_company_claims_do_not_expand_authority(self):
        executor = self._executor()
        token = self._token(jti="binding_123456789abcdefghij")

        with self.assertRaises(OrmToolError) as wrong_turn:
            executor.read_records(
                delegation_token=token,
                turn_id="22345678-1234-5678-1234-567812345678",
                model="res.country",
                record_ids=[self.allowed_country.id],
                fields=["name"],
            )
        self.assertEqual(wrong_turn.exception.code, "scope_denied")

        wrong_database = self._token(
            database="missing-m2-database",
            jti="database_12345678abcdefghij",
        )
        with self.assertRaises(OrmToolError) as database_failure:
            executor.read_records(
                delegation_token=wrong_database,
                turn_id=str(TURN_ID),
                model="res.country",
                record_ids=[self.allowed_country.id],
                fields=["name"],
            )
        self.assertEqual(database_failure.exception.code, "delegation_rejected")

        forged_company = self._token(
            company_id=self.company_b.id,
            allowed_company_ids=(self.company_b.id,),
            jti="company_123456789abcdefghij",
        )
        with self.assertRaises(OrmToolError) as company_failure:
            executor.read_records(
                delegation_token=forged_company,
                turn_id=str(TURN_ID),
                model="res.country",
                record_ids=[self.allowed_country.id],
                fields=["name"],
            )
        self.assertEqual(company_failure.exception.code, "delegation_rejected")

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
        self.assertIsInstance(result["label"], str)
        self.assertIsInstance(result["fields"]["display_name"]["searchable"], bool)
        self.assertIsInstance(result["fields"]["display_name"]["sortable"], bool)
        self.assertIsInstance(result["fields"]["display_name"]["groupable"], bool)

        read_token = self._token(
            model="res.users",
            record_ids=(self.user.id,),
            jti="field_0123456789abcdefghij",
        )
        with self.assertRaises(OrmToolError) as restricted:
            self._executor().read_records(
                delegation_token=read_token,
                turn_id=str(TURN_ID),
                model="res.users",
                record_ids=[self.user.id],
                fields=["request"],
            )
        # Odoo removes fields.NO_ACCESS from the effective _fields mapping, so a
        # restricted field is deliberately indistinguishable from an unknown one.
        self.assertEqual(restricted.exception.code, "invalid_fields")

    def test_company_b_record_is_hidden_from_company_a_delegation(self):
        token = self._token(
            model="res.partner",
            record_ids=(self.company_b_partner.id,),
            jti="multicompany_12345abcdefghij",
        )

        with self.assertRaises(OrmToolError) as failure:
            self._executor().read_records(
                delegation_token=token,
                turn_id=str(TURN_ID),
                model="res.partner",
                record_ids=[self.company_b_partner.id],
                fields=["name", "company_id"],
            )

        self.assertEqual(failure.exception.code, "access_denied")

    def test_each_read_scope_is_single_use(self):
        executor = self._executor()
        token = self._token(jti="replay_123456789abcdefghij")

        metadata = executor.get_model_metadata(
            delegation_token=token,
            turn_id=str(TURN_ID),
            model="res.country",
        )
        record = executor.read_records(
            delegation_token=token,
            turn_id=str(TURN_ID),
            model="res.country",
            record_ids=[self.allowed_country.id],
            fields=["name"],
        )
        self.assertTrue(metadata["ok"])
        self.assertTrue(record["ok"])

        for operation in ("metadata", "read"):
            with self.assertRaises(OrmToolError) as replayed:
                if operation == "metadata":
                    executor.get_model_metadata(
                        delegation_token=token,
                        turn_id=str(TURN_ID),
                        model="res.country",
                    )
                else:
                    executor.read_records(
                        delegation_token=token,
                        turn_id=str(TURN_ID),
                        model="res.country",
                        record_ids=[self.allowed_country.id],
                        fields=["name"],
                    )
            self.assertEqual(replayed.exception.code, "delegation_replayed")

    def test_runtime_ledger_is_unique_and_not_publicly_writable(self):
        ledger = self.env(user=self.user.id, su=False)["odoo.ai.delegation.use"]
        with self.assertRaises(AccessError):
            ledger.create(
                {
                    "expires_at": datetime.fromtimestamp(NOW + 60, UTC),
                    "jti": "public_123456789abcdefghij",
                    "scope": "fields_get",
                }
            )

        self.assertTrue(
            ledger._consume(
                jti="ledger_123456789abcdefghij",
                scope="fields_get",
                expires_at=NOW + 60,
            )
        )
        self.assertFalse(
            ledger._consume(
                jti="ledger_123456789abcdefghij",
                scope="fields_get",
                expires_at=NOW + 60,
            )
        )

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
