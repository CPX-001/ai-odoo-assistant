# Phase 2/3 real validation runbook

Executable companion to `REAL_ENV_VALIDATION_PROTOCOL.md` for the nine prepared P2/P3 gates.

## Environment

Use disposable Odoo 18 databases/data only:

```bash
export ODOO_BIN=/path/to/odoo-bin
export ODOO_CONF=/path/to/odoo.conf
export ODOO_AI_TEST_DB=odoo_ai_phase23_$(date +%Y%m%d_%H%M%S)
export ODOO_AI_ADDONS_PATH=/path/to/odoo/addons:/path/to/ai-odoo-assistant/addons
export ODOO_AI_HOOT_BASE_URL=http://127.0.0.1:8069
export ODOO_AI_HOOT_DB="$ODOO_AI_TEST_DB"
python tests/e2e/phase23_real_gate_check.py
```

If the installed Odoo exposes HOOT at a different URL, set `ODOO_AI_HOOT_URL` explicitly.

## Phase 2

For each gate, the runner prints the exact backend selector, browser filter, expectations, redaction and cleanup. Example:

```bash
python tests/e2e/phase23_real_gate_runner.py --gate P2-REAL-AUTH
python tests/e2e/phase23_real_gate_runner.py --gate P2-REAL-AUTH --execute-backend
export ODOO_AI_HOOT_FILTER='auth, ACL, timeout, tool failure and recovery produce distinct deterministic presentation'
node tests/e2e/phase23_hoot_gate.mjs
```

Repeat with:

```text
P2-REAL-AUTH
P2-REAL-ACL
P2-REAL-TIMEOUT
P2-REAL-TOOLFAIL
P2-REAL-RECOVERY
```

Backend success alone is not PASS. Record browser observation and sanitized evidence against the exact tested SHA.

## Phase 3 prepared commands

Do not use these as completion gates until Phase 2 is formally COMPLETE and Phase 3 production APIs exist:

```bash
python tests/e2e/phase23_real_gate_runner.py --gate P3-REAL-ACTIVITY-READ --execute-backend
python tests/e2e/phase23_real_gate_runner.py --gate P3-REAL-ACTIVITY-ACTION --execute-backend
python tests/e2e/phase23_real_gate_runner.py --gate P3-REAL-LIVE-VISIBILITY --execute-backend
python tests/e2e/phase23_real_gate_runner.py --gate P3-REAL-REDACTION --execute-backend
```

`phase3_real` tests are `-standard` so a normal addon battery cannot accidentally claim future-phase acceptance.

## Minimum surrounding battery

```bash
python -m pytest -q tests/unit
python -m pytest -q tests
python tests/e2e/phase23_real_gate_check.py
"$ODOO_BIN" -c "$ODOO_CONF" -d "$ODOO_AI_TEST_DB" \
  --addons-path="$ODOO_AI_ADDONS_PATH" -u odoo_ai_assistant \
  --test-enable --test-tags '/odoo_ai_assistant' --stop-after-init --log-level=test
```

Run the complete `@odoo_ai_assistant` HOOT suite after update as well as each filtered browser gate.

## Evidence/cleanup

Record tested SHA, Odoo/Codex/browser versions, user profile, observed machine failure/public event, expected browser behavior and result. Never retain passwords/tokens/raw prompts/provider stdout-stderr/unrestricted tool payloads/customer data.

After validation remove disposable DB, filestore, unsanitized logs/screenshots and temporary fault fixtures. Restore normal `odoo-server.service` and verify the normal login endpoint returns HTTP 200.
