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
from odoo.addons.odoo_ai_assistant.services.runtime_account import (
    runtime_status_payload,
)

env: Any = globals()["env"]

_DB_PREFIX = "odoo_ai_"
_REQUIRED_MODULE = "odoo_ai_phase2_faults"


def required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


def ensure_internal_user(
    *,
    login: str,
    password: str,
    name: str,
    extra_group_xmlids: tuple[str, ...] = (),
):
    group_user = env.ref("base.group_user")
    group_ids = [group_user.id]
    group_ids.extend(env.ref(xmlid).id for xmlid in extra_group_xmlids)
    company = env.company
    values = {
        "active": True,
        "company_id": company.id,
        "company_ids": [Command.set([company.id])],
        "groups_id": [Command.set(group_ids)],
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

# The deterministic terminal faults are injected after enqueue. Keep the normal
# database/account gate enabled and prove the installation-scoped Codex session is
# authenticated before creating browser users.
env["ir.config_parameter"].set_param(
    "odoo_ai_assistant.codex_connection_enabled", "true"
)
runtime_status = runtime_status_payload(env)
if runtime_status.get("state") != "authenticated":
    raise RuntimeError(
        "Phase 2 real gates require an authenticated Codex session before fault injection"
    )

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
    extra_group_xmlids=("base.group_partner_manager",),
)
limited_user = ensure_internal_user(
    login=limited_login,
    password=limited_password,
    name="Phase 2 Limited Failure User",
)

# ``odoo-bin shell`` rolls its cursor back on exit. Persist only this disposable
# database activation and its two test users before reporting the fixture ready.
env.cr.commit()

print(
    json.dumps(
        {
            "database": env.cr.dbname,
            "fixture_module": _REQUIRED_MODULE,
            "runtime_state": runtime_status["state"],
            "default_login": default_user.login,
            "limited_login": limited_user.login,
            "result": "READY_NOT_GATE_PASS",
        },
        sort_keys=True,
    )
)
