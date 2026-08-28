"""Prepare deterministic Phase 2 browser-gate users in a disposable Odoo shell.

Run only against an ``odoo_ai_*`` database with the test-only
``odoo_ai_phase2_faults`` addon installed. Passwords are read from environment and
never printed.
"""

from __future__ import annotations

import json
import os
from typing import Any

from odoo import Command


env: Any = globals()["env"]

_DB_PREFIX = "odoo_ai_"
_REQUIRED_MODULE = "odoo_ai_phase2_faults"


def required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


def ensure_internal_user(*, login: str, password: str, name: str):
    group_user = env.ref("base.group_user")
    company = env.company
    values = {
        "active": True,
        "company_id": company.id,
        "company_ids": [Command.set([company.id])],
        "groups_id": [Command.set([group_user.id])],
        "login": login,
        "name": name,
        "password": password,
        "share": False,
    }
    user = env["res.users"].search([("login", "=", login)], limit=1)
    if user:
        user.with_context(no_reset_password=True).write(values)
    else:
        user = env["res.users"].with_context(no_reset_password=True).create(values)
    return user


if not env.cr.dbname.startswith(_DB_PREFIX):
    raise RuntimeError("Phase 2 fixture setup requires a disposable odoo_ai_* database")
module = env["ir.module.module"].search([("name", "=", _REQUIRED_MODULE)], limit=1)
if not module or module.state != "installed":
    raise RuntimeError("odoo_ai_phase2_faults must be installed before fixture setup")

login = required("ODOO_AI_P2_LOGIN")
password = required("ODOO_AI_P2_PASSWORD")
limited_login = required("ODOO_AI_P2_LIMITED_LOGIN")
limited_password = required("ODOO_AI_P2_LIMITED_PASSWORD")
if login == limited_login:
    raise RuntimeError("default and limited Phase 2 test logins must differ")
default_user = ensure_internal_user(
    login=login,
    password=password,
    name="Phase 2 Failure User",
)
limited_user = ensure_internal_user(
    login=limited_login,
    password=limited_password,
    name="Phase 2 Limited Failure User",
)

print(
    json.dumps(
        {
            "database": env.cr.dbname,
            "fixture_module": _REQUIRED_MODULE,
            "default_login": default_user.login,
            "limited_login": limited_user.login,
            "result": "READY_NOT_GATE_PASS",
        },
        sort_keys=True,
    )
)
