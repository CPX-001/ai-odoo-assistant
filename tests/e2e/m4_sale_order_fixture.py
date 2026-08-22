"""Create or verify the disposable M4 sale.order fixture through an Odoo shell."""

from __future__ import annotations

import json
import os
from typing import Any

from odoo import Command

env: Any = globals()["env"]  # Provided by ``odoo-bin shell``.

LOGIN = os.environ.get("M4_E2E_LOGIN", "m4-e2e-sales-user")
DENIED_LOGIN = os.environ.get("M4_E2E_DENIED_LOGIN", "m4-e2e-other-sales-user")
PASSWORD = os.environ.get("M4_E2E_PASSWORD", "m4-e2e-disposable-password")
ORDER_REFERENCE = "ODOO-AI-M3-CREATE-TASK"
FIXTURE_PREFIX = "ODOO-AI-M4-E2E"


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


def _partner():
    partner = env["res.partner"].search([("ref", "=", FIXTURE_PREFIX)], limit=1)
    values = {
        "company_id": env.company.id,
        "name": "M4 E2E Customer",
        "ref": FIXTURE_PREFIX,
    }
    if partner:
        partner.write(values)
    else:
        partner = env["res.partner"].create(values)
    return partner


def _order(marker: str, owner, partner):
    reference = ORDER_REFERENCE if marker.endswith("ALLOWED") else marker
    order = env["sale.order"].search(
        [("client_order_ref", "=", reference), ("user_id", "=", owner.id)],
        limit=1,
    )
    values = {
        "client_order_ref": reference,
        "company_id": env.company.id,
        "partner_id": partner.id,
        "user_id": owner.id,
    }
    if order:
        order.write(values)
    else:
        order = env["sale.order"].create(values)
    return order


def _verify() -> None:
    order_id = int(os.environ["M4_ALLOWED_ORDER_ID"])
    order = env["sale.order"].browse(order_id).exists()
    user = env["res.users"].search([("login", "=", LOGIN)], limit=1)
    if not order or not user or order.user_id != user:
        raise RuntimeError("m4_fixture_record_unavailable")
    order.with_user(user).action_confirm()
    task_name = f"M3 diagnostic task for {order.name}"
    tasks = env["project.task"].search([("name", "=", task_name)])
    if len(tasks) != 1 or "visible M3 action_confirm" not in tasks.description:
        raise RuntimeError("m4_fixture_effect_missing")
    env.cr.commit()
    print(
        "M4_E2E_EFFECT="
        + json.dumps(
            {
                "order_id": order.id,
                "order_name": order.name,
                "order_state": order.state,
                "task_count": len(tasks),
                "task_name": task_name,
            },
            sort_keys=True,
        )
    )


if os.environ.get("M4_E2E_VERIFY_EFFECT") == "1":
    _verify()
else:
    partner = _partner()
    sales_user = _user(LOGIN, "M4 E2E Sales User")
    other_user = _user(DENIED_LOGIN, "M4 E2E Other Sales User")
    allowed_order = _order(f"{FIXTURE_PREFIX}-ALLOWED", sales_user, partner)
    denied_order = _order(f"{FIXTURE_PREFIX}-DENIED", other_user, partner)
    env.cr.commit()
    print(
        "M4_E2E_FIXTURE="
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
