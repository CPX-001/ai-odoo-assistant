from contextlib import contextmanager
from datetime import UTC, datetime
from uuid import UUID

from odoo import Command
from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, tagged

from ..security import QueryDelegationCodec, QueryDelegationPayload
from ..services.orm_tools import OrmToolError
from ..services.query_tools import DelegatedQueryToolExecutor

NOW = 1_787_337_600
SECRET = b"odoo-m5-query-delegation-secret-" + b"q" * 48
TURN_ID = UUID("32345678-1234-5678-1234-567812345678")


@tagged("post_install", "-at_install")
class TestDelegatedQueryTools(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company_b = cls.env["res.company"].create({"name": "M5 Query Company B"})
        cls.allowed_a = cls.env["res.partner"].create(
            {"name": "M5Q Allowed A", "color": 2, "company_id": cls.env.company.id}
        )
        cls.allowed_b = cls.env["res.partner"].create(
            {"name": "M5Q Allowed B", "color": 5, "company_id": cls.env.company.id}
        )
        cls.denied = cls.env["res.partner"].create(
            {"name": "M5Q Hidden", "color": 99, "company_id": cls.env.company.id}
        )
        cls.other_company = cls.env["res.partner"].create(
            {"name": "M5Q Other Company", "color": 77, "company_id": cls.company_b.id}
        )
        cls.query_group = cls.env["res.groups"].create({"name": "M5 query restricted"})
        cls.env["ir.rule"].create(
            {
                "name": "M5 query delegated partner rule",
                "model_id": cls.env["ir.model"]._get_id("res.partner"),
                "domain_force": f"[('id', 'in', [{cls.allowed_a.id}, {cls.allowed_b.id}, {cls.other_company.id}])]",
                "groups": [Command.link(cls.query_group.id)],
                "perm_read": True,
                "perm_write": False,
                "perm_create": False,
                "perm_unlink": False,
            }
        )
        cls.user = cls.env["res.users"].create(
            {
                "name": "M5 Query User",
                "login": "m5-query-user",
                "company_id": cls.env.company.id,
                "company_ids": [Command.set([cls.env.company.id])],
                "groups_id": [
                    Command.set(
                        [
                            cls.env.ref("base.group_user").id,
                            cls.query_group.id,
                        ]
                    )
                ],
            }
        )

    def _codec(self, now=NOW):
        return QueryDelegationCodec(SECRET, clock=lambda: now)

    def _token(
        self,
        *,
        model="res.partner",
        allowed_fields=("id", "color", "comment", "company_id", "name"),
        scopes=("query_schema", "query_records", "aggregate_records"),
        jti="query_0123456789abcdefgh",
        allowed_company_ids=None,
        max_records=50,
        max_fields=5,
        max_conditions=8,
        max_groups=50,
        max_aggregates=8,
    ):
        payload = QueryDelegationPayload(
            format_version=1,
            jti=jti,
            turn_id=TURN_ID,
            database=self.env.cr.dbname,
            uid=self.user.id,
            company_id=self.env.company.id,
            allowed_company_ids=allowed_company_ids or (self.env.company.id,),
            lang="en_US",
            model=model,
            allowed_fields=allowed_fields,
            scopes=scopes,
            issued_at=NOW,
            expires_at=NOW + 60,
            max_records=max_records,
            max_fields=max_fields,
            max_conditions=max_conditions,
            max_groups=max_groups,
            max_aggregates=max_aggregates,
            policy_revision="m5-query-read-v1",
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
        try:
            if (
                delegated.company.id != claims.company_id
                or tuple(delegated.companies.ids) != claims.allowed_company_ids
            ):
                raise OrmToolError("delegation_rejected", 403)
        except AccessError:
            raise OrmToolError("delegation_rejected", 403) from None
        yield delegated

    def _executor(self):
        consumed = set()

        def replay_guard(claims, scope):
            key = (claims.jti, scope)
            if key in consumed:
                raise OrmToolError("delegation_replayed", 403)
            consumed.add(key)

        return DelegatedQueryToolExecutor(
            codec=self._codec(),
            environment_provider=self._environment,
            replay_guard=replay_guard,
            observed_at=lambda: datetime.fromtimestamp(NOW, UTC),
        )

    def _record_query(self, **overrides):
        value = {
            "model": "res.partner",
            "fields": ["name", "color", "company_id"],
            "filter": {
                "match": "all",
                "conditions": [
                    {"field": "name", "operator": "contains", "value": "M5Q"}
                ],
            },
            "order": [{"field": "color", "direction": "desc"}],
            "limit": 10,
        }
        value.update(overrides)
        return value

    def test_filter_sort_record_rules_and_company_context_are_authoritative(self):
        result = self._executor().query_records(
            delegation_token=self._token(),
            turn_id=str(TURN_ID),
            payload=self._record_query(),
        )

        self.assertEqual(
            [row["id"] for row in result["records"]],
            [self.allowed_b.id, self.allowed_a.id],
        )
        self.assertNotIn(self.denied.id, [row["id"] for row in result["records"]])
        self.assertNotIn(
            self.other_company.id, [row["id"] for row in result["records"]]
        )
        self.assertFalse(result["truncated"])

    def test_aggregate_count_sum_and_group_cap_are_server_side(self):
        result = self._executor().aggregate_records(
            delegation_token=self._token(jti="query_aggregate_123456789"),
            turn_id=str(TURN_ID),
            payload={
                "model": "res.partner",
                "filter": {"match": "all", "conditions": []},
                "metrics": [
                    {"operation": "count", "field": None},
                    {"operation": "sum", "field": "color"},
                ],
                "group_by": ["company_id"],
                "group_limit": 10,
            },
        )

        self.assertEqual(result["returned_group_count"], 1)
        metrics = result["groups"][0]["metrics"]
        self.assertEqual(metrics[0]["value"], 2)
        self.assertEqual(metrics[1]["value"], 7)

    def test_sql_like_text_is_only_a_filter_value(self):
        result = self._executor().query_records(
            delegation_token=self._token(jti="query_injection_123456789"),
            turn_id=str(TURN_ID),
            payload=self._record_query(
                filter={
                    "match": "all",
                    "conditions": [
                        {
                            "field": "name",
                            "operator": "contains",
                            "value": "' OR 1=1 --",
                        }
                    ],
                }
            ),
        )

        self.assertEqual(result["records"], [])
        self.assertEqual(result["returned_count"], 0)

    def test_operator_field_model_caps_and_replay_fail_closed(self):
        with self.assertRaises(OrmToolError) as operator:
            self._executor().query_records(
                delegation_token=self._token(jti="query_operator_1234567890"),
                turn_id=str(TURN_ID),
                payload=self._record_query(
                    filter={
                        "match": "all",
                        "conditions": [
                            {"field": "name", "operator": "gt", "value": "M5Q"}
                        ],
                    }
                ),
            )
        self.assertEqual(operator.exception.code, "operator_not_allowed")

        with self.assertRaises(OrmToolError) as field:
            self._executor().query_records(
                delegation_token=self._token(jti="query_field_123456789012"),
                turn_id=str(TURN_ID),
                payload=self._record_query(fields=["email"]),
            )
        self.assertEqual(field.exception.code, "field_not_allowed")

        with self.assertRaises(OrmToolError) as model:
            self._executor().query_records(
                delegation_token=self._token(jti="query_model_123456789012"),
                turn_id=str(TURN_ID),
                payload=self._record_query(model="res.users"),
            )
        self.assertEqual(model.exception.code, "scope_denied")

        with self.assertRaises(OrmToolError) as cap:
            self._executor().query_records(
                delegation_token=self._token(
                    jti="query_cap_12345678901234", max_records=1
                ),
                turn_id=str(TURN_ID),
                payload=self._record_query(limit=2),
            )
        self.assertEqual(cap.exception.code, "limit_exceeded")

        executor = self._executor()
        token = self._token(jti="query_replay_12345678901")
        executor.query_records(
            delegation_token=token,
            turn_id=str(TURN_ID),
            payload=self._record_query(),
        )
        with self.assertRaises(OrmToolError) as replay:
            executor.query_records(
                delegation_token=token,
                turn_id=str(TURN_ID),
                payload=self._record_query(),
            )
        self.assertEqual(replay.exception.code, "delegation_replayed")

    def test_query_schema_is_bounded_by_signed_fields(self):
        result = self._executor().get_model_metadata(
            delegation_token=self._token(
                scopes=("query_schema",),
                allowed_fields=("id", "name"),
                max_fields=2,
            ),
            turn_id=str(TURN_ID),
            model="res.partner",
        )

        self.assertEqual(set(result["fields"]), {"id", "name"})
        self.assertNotIn("email", result["fields"])

    def test_query_authority_does_not_accept_a_legacy_token(self):
        from ..security import DelegationCodec, DelegationPayload

        legacy = DelegationCodec(SECRET, clock=lambda: NOW).encode(
            DelegationPayload(
                format_version=1,
                jti="legacy_0123456789abcdefg",
                turn_id=TURN_ID,
                database=self.env.cr.dbname,
                uid=self.user.id,
                company_id=self.env.company.id,
                allowed_company_ids=(self.env.company.id,),
                lang="en_US",
                model="res.partner",
                record_ids=(self.allowed_a.id,),
                scopes=("read_records",),
                issued_at=NOW,
                expires_at=NOW + 60,
                max_records=1,
                max_fields=1,
            )
        )
        with self.assertRaises(OrmToolError) as failure:
            self._executor().query_records(
                delegation_token=legacy,
                turn_id=str(TURN_ID),
                payload=self._record_query(fields=["name"], limit=1),
            )
        self.assertEqual(failure.exception.code, "delegation_rejected")
