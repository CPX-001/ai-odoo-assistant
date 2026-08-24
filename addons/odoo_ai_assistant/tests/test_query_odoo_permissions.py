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
SECRET = b"odoo-query-native-permissions-" + b"p" * 48
TURN_ID = UUID("72345678-1234-5678-9234-567812345678")
MARKER = "AI-NATIVE-PERMISSION-"


@tagged("post_install", "-at_install")
class TestQueryUsesNativeOdooPermissions(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        all_sales_group = cls.env.ref("sales_team.group_sale_salesman_all_leads")
        own_sales_group = cls.env.ref("sales_team.group_sale_salesman")
        internal_group = cls.env.ref("base.group_user")

        cls.query_user = cls.env["res.users"].create(
            {
                "name": "AI Query All Sales",
                "login": "ai-query-all-sales",
                "company_id": cls.env.company.id,
                "company_ids": [Command.set([cls.env.company.id])],
                "groups_id": [Command.set([internal_group.id, all_sales_group.id])],
            }
        )
        cls.other_salesperson = cls.env["res.users"].create(
            {
                "name": "AI Query Other Salesperson",
                "login": "ai-query-other-salesperson",
                "company_id": cls.env.company.id,
                "company_ids": [Command.set([cls.env.company.id])],
                "groups_id": [Command.set([internal_group.id, own_sales_group.id])],
            }
        )
        partner = cls.env["res.partner"].create({"name": "AI Permission Test Customer"})
        cls.owned_order = cls.env["sale.order"].create(
            {
                "partner_id": partner.id,
                "user_id": cls.query_user.id,
                "client_order_ref": f"{MARKER}OWN",
            }
        )
        cls.other_order = cls.env["sale.order"].create(
            {
                "partner_id": partner.id,
                "user_id": cls.other_salesperson.id,
                "client_order_ref": f"{MARKER}OTHER",
            }
        )

    def _codec(self):
        return QueryDelegationCodec(SECRET, clock=lambda: NOW)

    def _token(self):
        return self._codec().encode(
            QueryDelegationPayload(
                format_version=1,
                jti="native_permissions_0123456789",
                turn_id=TURN_ID,
                database=self.env.cr.dbname,
                uid=self.query_user.id,
                company_id=self.env.company.id,
                allowed_company_ids=(self.env.company.id,),
                lang="en_US",
                model="sale.order",
                allowed_fields=("id", "client_order_ref", "name", "user_id"),
                scopes=("query_records",),
                issued_at=NOW,
                expires_at=NOW + 60,
                max_records=10,
                max_fields=4,
                max_conditions=2,
                max_groups=10,
                max_aggregates=4,
                policy_revision="m5-query-read-v1",
            )
        )

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

    def test_non_owned_quotation_is_visible_when_odoo_allows_it(self):
        executor = DelegatedQueryToolExecutor(
            codec=self._codec(),
            environment_provider=self._environment,
            replay_guard=lambda claims, scope: None,
            observed_at=lambda: datetime.fromtimestamp(NOW, UTC),
        )

        result = executor.query_records(
            delegation_token=self._token(),
            turn_id=str(TURN_ID),
            payload={
                "model": "sale.order",
                "fields": ["name", "client_order_ref", "user_id"],
                "filter": {
                    "match": "all",
                    "conditions": [
                        {
                            "field": "client_order_ref",
                            "operator": "contains",
                            "value": MARKER,
                        }
                    ],
                },
                "order": [{"field": "name", "direction": "asc"}],
                "limit": 10,
            },
        )

        returned_ids = {row["id"] for row in result["records"]}
        self.assertIn(self.owned_order.id, returned_ids)
        self.assertIn(self.other_order.id, returned_ids)
