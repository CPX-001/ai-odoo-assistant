"""Create the disposable M2 sale.order acceptance fixture from an Odoo shell.

Run with ``odoo-bin shell -d <db> < tests/e2e/m2_sale_order_fixture.py``.
The script is idempotent and intentionally uses the shell's authoritative ORM
environment without ``sudo()``.
"""

from __future__ import annotations

import json
import os
from typing import Any

from odoo import Command

env: Any = globals()["env"]  # Provided by ``odoo-bin shell``.

LOGIN = os.environ.get("M2_E2E_LOGIN", "m2-e2e-sales-user")
DENIED_LOGIN = os.environ.get("M2_E2E_DENIED_LOGIN", "m2-e2e-other-sales-user")
PASSWORD = os.environ.get("M2_E2E_PASSWORD", "m2-e2e-disposable-password")
FIXTURE_REF = "ODOO-AI-M2-E2E"


def _user(login: str, name: str):
    groups = [
        env.ref("base.group_user").id,
        env.ref("sales_team.group_sale_salesman").id,
    ]
    values = {
        "active": True,
        "company_id": env.company.id,
        "company_ids": [Command.set([env.company.id])],
        "groups_id": [Command.set(groups)],
        "login": login,
        "name": name,
        "password": PASSWORD,
    }
    user = env["res.users"].search([("login", "=", login)], limit=1)
    if user:
        user.write(values)
    else:
        user = env["res.users"].with_context(no_reset_password=True).create(values)
    return user


partner = env["res.partner"].search([("ref", "=", FIXTURE_REF)], limit=1)
if partner:
    partner.write({"company_id": env.company.id, "name": "M2 E2E Customer"})
else:
    partner = env["res.partner"].create(
        {
            "company_id": env.company.id,
            "name": "M2 E2E Customer",
            "ref": FIXTURE_REF,
        }
    )

sales_user = _user(LOGIN, "M2 E2E Sales User")
other_user = _user(DENIED_LOGIN, "M2 E2E Other Sales User")


def _order(marker: str, owner):
    order = env["sale.order"].search([("client_order_ref", "=", marker)], limit=1)
    values = {
        "client_order_ref": marker,
        "company_id": env.company.id,
        "partner_id": partner.id,
        "user_id": owner.id,
    }
    if order:
        order.write(values)
    else:
        order = env["sale.order"].create(values)
    return order


allowed_order = _order(f"{FIXTURE_REF}-ALLOWED", sales_user)
denied_order = _order(f"{FIXTURE_REF}-DENIED", other_user)
env.cr.commit()

print(
    "M2_E2E_FIXTURE="
    + json.dumps(
        {
            "allowed_order_id": allowed_order.id,
            "allowed_order_name": allowed_order.name,
            "database": env.cr.dbname,
            "denied_order_id": denied_order.id,
            "denied_order_name": denied_order.name,
            "login": sales_user.login,
            "uid": sales_user.id,
        },
        sort_keys=True,
    )
)
