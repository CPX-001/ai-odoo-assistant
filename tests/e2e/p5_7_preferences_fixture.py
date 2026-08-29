"""Prepare one internal user for P5.7 real browser gates in a disposable DB."""

from __future__ import annotations

import json
import os
from typing import Any

from odoo import Command
from odoo.addons.odoo_ai_assistant.services.runtime_account import runtime_status_payload

env: Any = globals()["env"]


def required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


if not env.cr.dbname.startswith("odoo_ai_"):
    raise RuntimeError("P5.7 fixture setup requires a disposable odoo_ai_* database")

runtime = runtime_status_payload(env)
if runtime.get("state") != "authenticated":
    raise RuntimeError("P5.7 real gates require the authenticated primary host Codex session")

login = required("ODOO_AI_P5_LOGIN")
password = required("ODOO_AI_P5_PASSWORD")
company = env.company
values = {
    "active": True,
    "company_id": company.id,
    "company_ids": [Command.set([company.id])],
    "groups_id": [Command.set([env.ref("base.group_user").id])],
    "login": login,
    "name": "P5.7 Conversation Preference User",
    "password": password,
    "share": False,
}
user = env["res.users"].search([("login", "=", login)], limit=1)
if user:
    user.with_context(no_reset_password=True).write(values)
else:
    user = env["res.users"].with_context(no_reset_password=True).create(values)
env["odoo.ai.user.preference"].with_user(user).set_current_agent_profile("balanced")
env.cr.commit()

print(
    json.dumps(
        {
            "database": env.cr.dbname,
            "login": user.login,
            "runtime_state": runtime["state"],
            "result": "READY_NOT_GATE_PASS",
        },
        sort_keys=True,
    )
)
