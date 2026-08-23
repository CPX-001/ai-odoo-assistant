"""Create deterministic users and ACL-separated records in disposable Odoo."""

from __future__ import annotations

import json
import os
from typing import Any

from odoo import Command

env: Any = globals()["env"]
PASSWORD = os.environ["M5_E2E_PASSWORD"]


def _user(login: str, name: str):
    values = {
        "active": True,
        "company_id": env.company.id,
        "company_ids": [Command.set([env.company.id])],
        "groups_id": [Command.set([env.ref("base.group_user").id])],
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


def _item(name: str, code: str, state: str, owner):
    model = env["odoo.ai.m5.guided.item"]
    item = model.search([("guide_code", "=", code)], limit=1)
    values = {
        "company_id": env.company.id,
        "guide_code": code,
        "name": name,
        "owner_id": owner.id,
        "state": state,
    }
    if item:
        item.write(values)
    else:
        item = model.create(values)
    return item


login_a = os.environ["M5_E2E_LOGIN_A"]
login_b = os.environ["M5_E2E_LOGIN_B"]
user_a = _user(login_a, "M5 Query User A")
user_b = _user(login_b, "M5 Query User B")
visible_a = (
    _item("Visible Alpha", "M5-A-OPEN-1", "open", user_a),
    _item("Visible Beta", "M5-A-OPEN-2", "open", user_a),
    _item("Visible Done", "M5-A-DONE-1", "done", user_a),
)
hidden = _item("FORBIDDEN M5 HIDDEN RECORD", "M5-B-SECRET-1", "open", user_b)
menu = env.ref("odoo_ai_m5_guided_items.menu_m5_guided_items")
action = env.ref("odoo_ai_m5_guided_items.action_m5_guided_items")
env.cr.commit()
print(
    "M5_E2E_FIXTURE="
    + json.dumps(
        {
            "action_id": action.id,
            "hidden_id": hidden.id,
            "hidden_name": hidden.name,
            "login_a": login_a,
            "login_b": login_b,
            "menu_id": menu.id,
            "model": "odoo.ai.m5.guided.item",
            "user_a_id": user_a.id,
            "user_b_id": user_b.id,
            "visible_a_ids": [item.id for item in visible_a],
        },
        sort_keys=True,
    )
)
