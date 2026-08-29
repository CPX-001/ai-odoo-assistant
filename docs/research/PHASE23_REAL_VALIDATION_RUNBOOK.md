# Phase 2/3 real validation runbook

Executable companion to `REAL_ENV_VALIDATION_PROTOCOL.md` for the nine prepared P2/P3 gates.

The Phase 2 gates below use a **test-only Odoo fixture addon** under
`tests/fixtures/odoo18/odoo_ai_phase2_faults`. It is not a product dependency, does not add a second
runtime/tool registry, and is inert unless both of these conditions are true:

```text
ODOO_AI_PHASE2_FAULT_FIXTURE=1
database name starts with odoo_ai_
```

The fixture lets the real browser -> Odoo RPC -> persisted turn -> cron -> embedded runtime ->
terminal turn -> browser path be exercised without depending on random network/provider failures.
It never makes a real gate PASS by itself.

## 1. Environment

Use only disposable Odoo 18 databases and test credentials.

```bash
export REPO=/path/to/ai-odoo-assistant
export ODOO_BIN=/path/to/odoo-bin
export ODOO_CONF=/path/to/odoo.conf
export ODOO_AI_TEST_DB=odoo_ai_phase23_$(date +%Y%m%d_%H%M%S)
export ODOO_AI_P2_DB="$ODOO_AI_TEST_DB"
export ODOO_AI_ADDONS_PATH="/path/to/odoo/addons,$REPO/addons,$REPO/tests/fixtures/odoo18"
export ODOO_AI_P2_BASE_URL=http://127.0.0.1:8069
export ODOO_AI_HOOT_BASE_URL=http://127.0.0.1:8069
export ODOO_AI_HOOT_DB="$ODOO_AI_TEST_DB"

# Disposable browser users; do not reuse production credentials.
export ODOO_AI_P2_LOGIN=p2_failure_user
export ODOO_AI_P2_PASSWORD='replace-with-disposable-password'
export ODOO_AI_P2_LIMITED_LOGIN=p2_limited_user
export ODOO_AI_P2_LIMITED_PASSWORD='replace-with-another-disposable-password'
```

`--addons-path` uses Odoo's comma-separated syntax. Do not point a production database at the test
fixture directory.

Validate the manifest before touching Odoo:

```bash
cd "$REPO"
python tests/e2e/phase23_real_gate_check.py
```

## 2. Create/install the disposable database

Stop the normal service if it owns the same HTTP port. Do not delete or replace a customer database.

```bash
sudo systemctl stop odoo-server.service
createdb "$ODOO_AI_TEST_DB"

"$ODOO_BIN" -c "$ODOO_CONF" -d "$ODOO_AI_TEST_DB" \
  --addons-path="$ODOO_AI_ADDONS_PATH" \
  -i odoo_ai_assistant,odoo_ai_phase2_faults \
  --stop-after-init --log-level=test
```

The machine must already have the supported Codex executable and an authenticated primary host
session exposed to Odoo through `CODEX_HOME`. The deterministic faults are injected **after** the
normal `/turn` authentication precondition, so the fixture fails unless the real runtime status is
`authenticated`; no per-database activation is required.

Create the two disposable internal users and verify that prerequisite:

```bash
"$ODOO_BIN" shell -c "$ODOO_CONF" -d "$ODOO_AI_TEST_DB" \
  --addons-path="$ODOO_AI_ADDONS_PATH" \
  < "$REPO/tests/e2e/phase2_real_fixture.py"
```

Expected final JSON includes:

```text
"runtime_state": "authenticated"
"result": "READY_NOT_GATE_PASS"
```

No password is printed by the setup script.

## 3. Focused deterministic/Odoo regressions

These focused Odoo tests are useful surrounding regression checks; passing one is not the real gate.
For each Phase 2 gate:

```bash
python tests/e2e/phase23_real_gate_runner.py --gate P2-REAL-AUTH --execute-backend
python tests/e2e/phase23_real_gate_runner.py --gate P2-REAL-ACL --execute-backend
python tests/e2e/phase23_real_gate_runner.py --gate P2-REAL-TIMEOUT --execute-backend
python tests/e2e/phase23_real_gate_runner.py --gate P2-REAL-TOOLFAIL --execute-backend
python tests/e2e/phase23_real_gate_runner.py --gate P2-REAL-RECOVERY --execute-backend
```

Run the complete addon test battery before the browser trials:

```bash
"$ODOO_BIN" -c "$ODOO_CONF" -d "$ODOO_AI_TEST_DB" \
  --addons-path="$ODOO_AI_ADDONS_PATH" \
  -u odoo_ai_assistant \
  --test-enable --test-tags '/odoo_ai_assistant' \
  --stop-after-init --log-level=test
```

Record failures/errors/skips exactly; do not reinterpret unexecuted tests as PASS.

## 4. Start the real disposable product path with fault injection enabled

The environment flag belongs to this disposable Odoo process only. The fixture still refuses to arm
unless the database name begins with `odoo_ai_`.

Run this in a dedicated terminal (or equivalent supervised disposable process):

```bash
cd "$REPO"
ODOO_AI_PHASE2_FAULT_FIXTURE=1 \
"$ODOO_BIN" -c "$ODOO_CONF" -d "$ODOO_AI_TEST_DB" \
  --addons-path="$ODOO_AI_ADDONS_PATH" \
  --http-port=8069 --max-cron-threads=2
```

Wait until `http://127.0.0.1:8069/web/login?db=$ODOO_AI_TEST_DB` responds normally before continuing.
The tests rely on the actual Odoo cron/turn queue; they do not simulate progress with browser timers.

## 5. Execute the five Phase 2 real browser gates

Each command logs in through the real Odoo web UI, opens the Assistant, sends the exact deterministic
fault marker, captures the actual `/odoo_ai/v1/turn` id, waits for the real terminal UI, reads the
real `/odoo_ai/v1/turn/status`, checks the structured failure fields, checks deterministic copy and
retry visibility, and checks redaction.

```bash
python tests/e2e/phase23_real_gate_runner.py --gate P2-REAL-AUTH --execute-browser
python tests/e2e/phase23_real_gate_runner.py --gate P2-REAL-ACL --execute-browser
python tests/e2e/phase23_real_gate_runner.py --gate P2-REAL-TIMEOUT --execute-browser
python tests/e2e/phase23_real_gate_runner.py --gate P2-REAL-TOOLFAIL --execute-browser
python tests/e2e/phase23_real_gate_runner.py --gate P2-REAL-RECOVERY --execute-browser
```

Equivalent direct commands are:

```bash
node tests/e2e/phase2_real_failure_browser.mjs --gate P2-REAL-AUTH
node tests/e2e/phase2_real_failure_browser.mjs --gate P2-REAL-ACL
node tests/e2e/phase2_real_failure_browser.mjs --gate P2-REAL-TIMEOUT
node tests/e2e/phase2_real_failure_browser.mjs --gate P2-REAL-TOOLFAIL
node tests/e2e/phase2_real_failure_browser.mjs --gate P2-REAL-RECOVERY
```

A successful browser script intentionally reports:

```text
"result": "OBSERVED_OK_NOT_AUTOMATIC_PASS"
```

That means the expected product observation was obtained. The roadmap gate becomes PASS only after
that observation is recorded as sanitized evidence against the exact tested Git SHA and surrounding
required batteries are acceptable.

### Fault semantics

`P2-REAL-AUTH`
: `__P2_REAL_AUTH__` injects a bounded carried authentication failure after enqueue. Expected
  `failed / codex_turn_failed / authentication / none / after_change / reconnect`; no retry button.

`P2-REAL-ACL`
: `__P2_REAL_ACL__` performs a real ORM read as the limited originating user against
  `odoo.ai.phase2.secret`, whose access CSV grants read only to `base.group_system`. Expected
  `failed / access_denied / odoo_access / none / after_change / request_access`. If access
  unexpectedly succeeds, the fixture raises a different failure so the gate cannot false-pass.

`P2-REAL-TIMEOUT`
: `__P2_REAL_TIMEOUT__` injects a carried timeout before effects. Expected
  `failed / engine_timeout / provider_connection / none / safe / retry` and the browser retry
  control is visible.

`P2-REAL-TOOLFAIL`
: `__P2_REAL_TOOLFAIL__` raises bounded `capability_execution_failed`. Expected
  `failed / capability_execution / none / unknown / review`; no retry control.

`P2-REAL-RECOVERY`
: `__P2_REAL_RECOVERY__` commits only the turn's durable write barrier in a short test cursor and
  raises `worker_lost_after_write_barrier`. No business record is mutated. Expected
  `recovery_required / queue_worker / unknown / never / review`; the UI must state uncertainty and
  must not expose blind replay.

## 6. Supplemental HOOT coverage

HOOT is still required as the frontend regression suite, but it is not substituted for the real
product-path browser gate above.

For the focused P2.4 tests:

```bash
export ODOO_AI_HOOT_FILTER='auth, ACL, timeout, tool failure and recovery produce distinct deterministic presentation'
node tests/e2e/phase23_hoot_gate.mjs

export ODOO_AI_HOOT_FILTER='safe retry requires explicit retryability, safe effect state and retry action'
node tests/e2e/phase23_hoot_gate.mjs
```

Also run the complete `@odoo_ai_assistant` HOOT suite in the installed Odoo 18 environment and record
its actual totals.

## 7. Phase 3 prepared commands

Do **not** execute these as completion gates until all five Phase 2 gates are formally PASS and Phase
3 production persistence/browser APIs have been selected and implemented:

```bash
python tests/e2e/phase23_real_gate_runner.py --gate P3-REAL-ACTIVITY-READ --execute-backend
python tests/e2e/phase23_real_gate_runner.py --gate P3-REAL-ACTIVITY-ACTION --execute-backend
python tests/e2e/phase23_real_gate_runner.py --gate P3-REAL-LIVE-VISIBILITY --execute-backend
python tests/e2e/phase23_real_gate_runner.py --gate P3-REAL-REDACTION --execute-backend
```

The `phase3_real` Odoo tests are `-standard` so a normal addon battery cannot accidentally claim
future-phase acceptance. `P3-REAL-LIVE-VISIBILITY` is specifically prepared to require a second
connection to see a public event before the main worker transaction commits; browser timers are not
liveness evidence.

## 8. Minimum surrounding non-real battery

Run what the machine supports and record exact results/skips:

```bash
cd "$REPO"
python -m compileall -q addons/odoo_ai_assistant tests
python -m pytest -q tests/unit
python -m pytest -q tests
python tests/e2e/phase23_real_gate_check.py
node tests/js/failure_contract_test.mjs
node tests/js/public_activity_contract_test.mjs
git diff --check
```

Do not call any command PASS unless it actually ran on the tested checkpoint.

## 9. Evidence

For every real gate record at minimum:

```text
validation_id:
commit_tested:
date:
odoo_version:
codex_version:
browser_version:
user_profile:
result: PASS | FAIL | BLOCKED
observed_backend:
observed_browser:
redaction_observed:
expected:
artifact_refs:
notes:
```

Do not retain passwords/tokens/raw prompts/provider stdout-stderr/unrestricted tool arguments/results
or customer data. The fault markers and bounded machine fields are sufficient evidence.

If a gate fails, repair the cause, add deterministic regression coverage, update the disposable DB,
and rerun **that same gate** on the repaired SHA before moving on.

## 10. Cleanup and service restoration

Stop the disposable Odoo process, then remove its database, filestore and temporary unsanitized logs.
Use the actual configured Odoo data directory; the following is schematic and must point only at the
disposable database's filestore:

```bash
dropdb "$ODOO_AI_TEST_DB"
rm -rf "/path/to/odoo-data-dir/filestore/$ODOO_AI_TEST_DB"
rm -f /tmp/odoo-ai-phase2-*.log
sudo systemctl start odoo-server.service
curl --fail --silent --show-error http://127.0.0.1:8069/web/login >/dev/null
```

The final `curl` must succeed before validation handoff. Never delete a non-disposable database or
filestore while following this runbook.
