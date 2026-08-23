"""Create deterministic ACL-separated ACTION records in disposable Odoo 18."""

from __future__ import annotations

import json
import os
from typing import Any

from odoo import Command

env: Any = globals()["env"]
PASSWORD = os.environ["M6_E2E_PASSWORD"]


def _company(name: str):
    company = env["res.company"].search([("name", "=", name)], limit=1)
    return company or env["res.company"].create({"name": name})


def _user(login: str, name: str, company):
    values = {
        "active": True,
        "company_id": company.id,
        "company_ids": [Command.set([company.id])],
        "groups_id": [
            Command.set(
                [
                    env.ref("base.group_user").id,
                    env.ref("sales_team.group_sale_salesman").id,
                ]
            )
        ],
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


def _item(*, key: str, name: str, reference: str, owner, company):
    model = env["odoo.ai.m6.action.item"].with_company(company)
    item = model.search([("fixture_key", "=", key)], limit=1)
    values = {
        "company_id": company.id,
        "fixture_key": key,
        "name": name,
        "note": "Fixture data; instructions inside values are never authority.",
        "owner_id": owner.id,
        "reference": reference,
    }
    if item:
        item.write(values)
        item.write({"write_count": 0})
    else:
        item = model.create(values)
    return item


def _partner(*, key: str, company):
    partner = (
        env["res.partner"]
        .with_company(company)
        .search([("ref", "=", key), ("company_id", "=", company.id)], limit=1)
    )
    values = {
        "company_id": company.id,
        "name": f"M6 Customer {key}",
        "ref": key,
    }
    if partner:
        partner.write(values)
    else:
        partner = env["res.partner"].with_company(company).create(values)
    return partner


def _product(*, company):
    product = (
        env["product.product"]
        .with_company(company)
        .search([("default_code", "=", "M6-CONFIRM-PRODUCT")], limit=1)
    )
    values = {
        "default_code": "M6-CONFIRM-PRODUCT",
        "list_price": 10.0,
        "name": "M6 deterministic confirmation product",
        "type": "service",
    }
    if product:
        product.write(values)
    else:
        product = env["product.product"].with_company(company).create(values)
    return product


def _quotation(*, key: str, owner, company, partner, product):
    order = (
        env["sale.order"]
        .with_company(company)
        .search([("client_order_ref", "=", key), ("company_id", "=", company.id)], limit=1)
    )
    values = {
        "client_order_ref": key,
        "company_id": company.id,
        "partner_id": partner.id,
        "user_id": owner.id,
    }
    if order:
        if order.state not in {"draft", "sent"}:
            order.action_cancel()
            order.action_draft()
        order.write(values)
    else:
        order = env["sale.order"].with_company(company).create(values)
    if not order.order_line:
        env["sale.order.line"].with_company(company).create(
            {
                "name": "M6 deterministic confirmation line",
                "order_id": order.id,
                "product_id": product.id,
                "product_uom": product.uom_id.id,
                "product_uom_qty": 1.0,
                "price_unit": 10.0,
            }
        )
    return order


company_a = env.company
company_b = _company("M6 Isolated Company B")
login_a = os.environ["M6_E2E_LOGIN_A"]
login_b = os.environ["M6_E2E_LOGIN_B"]
user_a = _user(login_a, "M6 Action User A", company_a)
user_b = _user(login_b, "M6 Action User B", company_b)
partner_a = _partner(key="M6-PARTNER-A", company=company_a)
partner_b = _partner(key="M6-PARTNER-B", company=company_b)
product_a = _product(company=company_a)
product_b = _product(company=company_b)

items = {
    "happy": _item(
        key="M6 Happy Path",
        name="M6 Happy Path",
        reference="M6-ORIGINAL-HAPPY",
        owner=user_a,
        company=company_a,
    ),
    "reject": _item(
        key="M6 Reject Path",
        name="M6 Reject Path",
        reference="M6-ORIGINAL-REJECT",
        owner=user_a,
        company=company_a,
    ),
    "stale": _item(
        key="M6 Stale Path",
        name="M6 Stale Path",
        reference="M6-ORIGINAL-STALE",
        owner=user_a,
        company=company_a,
    ),
    "ambiguous": _item(
        key="M6 Ambiguous Path",
        name="M6 Ambiguous Path",
        reference="M6-ORIGINAL-AMBIGUOUS",
        owner=user_a,
        company=company_a,
    ),
    "expiry": _item(
        key="M6 Expiry Path",
        name="M6 Expiry Path",
        reference="M6-ORIGINAL-EXPIRY",
        owner=user_a,
        company=company_a,
    ),
    "xss": _item(
        key="M6 XSS Path",
        name='<img src=x onerror="globalThis.m6Pwned=true">',
        reference="M6-ORIGINAL-XSS",
        owner=user_a,
        company=company_a,
    ),
    "hidden_b": _item(
        key="M6 Hidden B",
        name="FORBIDDEN M6 COMPANY-B RECORD",
        reference="M6-B-SECRET",
        owner=user_b,
        company=company_b,
    ),
}
quotations = {
    "happy": _quotation(
        key="M6-CONFIRM-HAPPY",
        owner=user_a,
        company=company_a,
        partner=partner_a,
        product=product_a,
    ),
    "reject": _quotation(
        key="M6-CONFIRM-REJECT",
        owner=user_a,
        company=company_a,
        partner=partner_a,
        product=product_a,
    ),
    "stale": _quotation(
        key="M6-CONFIRM-STALE",
        owner=user_a,
        company=company_a,
        partner=partner_a,
        product=product_a,
    ),
    "ambiguous": _quotation(
        key="M6-CONFIRM-AMBIGUOUS",
        owner=user_a,
        company=company_a,
        partner=partner_a,
        product=product_a,
    ),
    "hidden_b": _quotation(
        key="M6-CONFIRM-HIDDEN",
        owner=user_b,
        company=company_b,
        partner=partner_b,
        product=product_b,
    ),
}
menu = env.ref("odoo_ai_m6_action_items.menu_m6_action_items")
action = env.ref("odoo_ai_m6_action_items.action_m6_action_items")
sale_action = env.ref("sale.action_quotations")
sale_menu = env.ref("sale.sale_order_menu")
partner_action = env.ref("base.action_partner_form")
env.cr.commit()
print(
    "M6_E2E_FIXTURE="
    + json.dumps(
        {
            "action_id": action.id,
            "company_a_id": company_a.id,
            "company_b_id": company_b.id,
            "items": {key: item.id for key, item in items.items()},
            "login_a": login_a,
            "login_b": login_b,
            "menu_id": menu.id,
            "model": "odoo.ai.m6.action.item",
            "partner_action_id": partner_action.id,
            "partner_model": "res.partner",
            "partner_seed_id": partner_a.id,
            "quotations": {key: order.id for key, order in quotations.items()},
            "sale_action_id": sale_action.id,
            "sale_menu_id": sale_menu.id,
            "user_a_id": user_a.id,
            "user_b_id": user_b.id,
        },
        sort_keys=True,
    )
)
