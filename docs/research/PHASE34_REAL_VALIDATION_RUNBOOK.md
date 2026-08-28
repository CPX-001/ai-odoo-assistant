# Phase 3/4 real validation runbook

Date: 2026-08-28  
Status: executable validation handoff; **not PASS evidence**

This runbook continues `PHASE23_REAL_VALIDATION_RUNBOOK.md`. The repository now contains the
production Phase 3 public-activity path and the Phase 4 provisional answer-stream path so one Odoo
18 validation session can test the downstream implementation after Phase 2 has passed.

Formal roadmap ordering is unchanged:

```text
five P2-REAL PASS on tested SHA
  -> four P3-REAL may count
      -> four P4-REAL may count
```

The code is present before those gates solely to make the requested validation batch reproducible.
A successful script prints `OBSERVED_OK_NOT_AUTOMATIC_PASS`; record sanitized evidence against the
exact SHA before changing any formal phase state.

## 1. Environment

Use a disposable Odoo 18 database only.

```bash
export REPO=/path/to/ai-odoo-assistant
export ODOO_BIN=/path/to/odoo-bin
export ODOO_CONF=/path/to/odoo.conf
export ODOO_AI_TEST_DB=odoo_ai_phase234_$(date +%Y%m%d_%H%M%S)
export ODOO_AI_ADDONS_PATH="/path/to/odoo/addons,$REPO/addons,$REPO/tests/fixtures/odoo18"

export ODOO_AI_P2_DB="$ODOO_AI_TEST_DB"
export ODOO_AI_P2_BASE_URL=http://127.0.0.1:8069
export ODOO_AI_P2_LOGIN=p2_failure_user
export ODOO_AI_P2_PASSWORD='replace-with-disposable-password'
export ODOO_AI_P2_LIMITED_LOGIN=p2_limited_user
export ODOO_AI_P2_LIMITED_PASSWORD='replace-with-another-disposable-password'

export ODOO_AI_P3_DB="$ODOO_AI_TEST_DB"
export ODOO_AI_P3_BASE_URL=http://127.0.0.1:8069
export ODOO_AI_P3_LOGIN="$ODOO_AI_P2_LOGIN"
export ODOO_AI_P3_PASSWORD="$ODOO_AI_P2_PASSWORD"
# Must describe one harmless reversible change to a disposable record that the test user can edit.
export ODOO_AI_P3_ACTION_PROMPT='Actualiza el teléfono del contacto desechable Phase 34 Demo a 5550102.'

export ODOO_AI_P4_DB="$ODOO_AI_TEST_DB"
export ODOO_AI_P4_BASE_URL=http://127.0.0.1:8069
export ODOO_AI_P4_LOGIN="$ODOO_AI_P3_LOGIN"
export ODOO_AI_P4_PASSWORD="$ODOO_AI_P3_PASSWORD"

export ODOO_AI_HOOT_DB="$ODOO_AI_TEST_DB"
export ODOO_AI_HOOT_BASE_URL=http://127.0.0.1:8069
```

Record the exact Git SHA, Odoo 18 build, Codex version and browser/Playwright version before running
acceptance gates.

## 2. Static/dependency-light preparation

From the exact checkout under test:

```bash
cd "$REPO"
python -m compileall -q addons/odoo_ai_assistant tests
python -m pytest -q tests/unit
python tests/e2e/phase23_real_gate_check.py
python tests/e2e/phase4_real_gate_check.py
node --check tests/e2e/phase2_real_failure_browser.mjs
node --check tests/e2e/phase3_real_activity_browser.mjs
node --check tests/e2e/phase4_real_answer_browser.mjs
node tests/js/failure_contract_test.mjs
node tests/js/public_activity_contract_test.mjs
git diff --check
```

Run the full dependency-light collection if its dependencies are installed:

```bash
python -m pytest -q tests
```

Do not convert missing dependencies or skipped real tests into PASS.

## 3. Install/update Odoo and focused integration tests

Create/install the disposable database exactly as described in `PHASE23_REAL_VALIDATION_RUNBOOK.md`,
including `odoo_ai_phase2_faults` for the Phase 2 fault gates. Then run the normal addon update and
full addon battery:

```bash
"$ODOO_BIN" -c "$ODOO_CONF" -d "$ODOO_AI_TEST_DB" \
  --addons-path="$ODOO_AI_ADDONS_PATH" \
  -u odoo_ai_assistant \
  --test-enable --test-tags '/odoo_ai_assistant' \
  --stop-after-init --log-level=test
```

Focused Phase 3 production projection:

```bash
"$ODOO_BIN" -c "$ODOO_CONF" -d "$ODOO_AI_TEST_DB" \
  --addons-path="$ODOO_AI_ADDONS_PATH" \
  -u odoo_ai_assistant --test-enable \
  --test-tags '/odoo_ai_assistant:TestPhase3PublicActivityProjection' \
  --stop-after-init --log-level=test
```

Focused Phase 4 live projection:

```bash
"$ODOO_BIN" -c "$ODOO_CONF" -d "$ODOO_AI_TEST_DB" \
  --addons-path="$ODOO_AI_ADDONS_PATH" \
  -u odoo_ai_assistant --test-enable \
  --test-tags '/odoo_ai_assistant:TestPhase4LiveProjection' \
  --stop-after-init --log-level=test
```

The Phase 3 second-cursor test is important: the worker cursor remains uncommitted while another
connection reads the independent public event. The production live table deliberately stores the
committed turn binding without a foreign key to the mutable turn row, avoiding an FK lock that could
otherwise destroy pre-final visibility. No `cr.commit()` is issued on the business cursor for UX.

## 4. Start the disposable real product

For Phase 2 fault gates, start with the fixture environment flag as documented in the Phase 2/3
runbook. After the five P2 gates have passed and their evidence is captured, restart the disposable
server **without** the Phase 2 fault-injection flag for Phase 3/4 normal behavior:

```bash
"$ODOO_BIN" -c "$ODOO_CONF" -d "$ODOO_AI_TEST_DB" \
  --addons-path="$ODOO_AI_ADDONS_PATH" \
  --http-port=8069 --max-cron-threads=2
```

Verify `/web/login` is healthy before browser gates. Codex must be authenticated through the
supported product path.

## 5. Phase 2 acceptance prerequisite

Run all five existing real gates first:

```bash
python tests/e2e/phase23_real_gate_runner.py --gate P2-REAL-AUTH --execute-backend --execute-browser
python tests/e2e/phase23_real_gate_runner.py --gate P2-REAL-ACL --execute-backend --execute-browser
python tests/e2e/phase23_real_gate_runner.py --gate P2-REAL-TIMEOUT --execute-backend --execute-browser
python tests/e2e/phase23_real_gate_runner.py --gate P2-REAL-TOOLFAIL --execute-backend --execute-browser
python tests/e2e/phase23_real_gate_runner.py --gate P2-REAL-RECOVERY --execute-backend --execute-browser
```

Do not count any Phase 3 result as acceptance until those five observations are formally recorded
PASS for the same tested SHA.

## 6. Phase 3 real gates

Backend/second-connection harness plus real browser observation:

```bash
python tests/e2e/phase23_real_gate_runner.py --gate P3-REAL-ACTIVITY-READ --execute-backend --execute-browser
python tests/e2e/phase23_real_gate_runner.py --gate P3-REAL-ACTIVITY-ACTION --execute-backend --execute-browser
python tests/e2e/phase23_real_gate_runner.py --gate P3-REAL-LIVE-VISIBILITY --execute-backend --execute-browser
python tests/e2e/phase23_real_gate_runner.py --gate P3-REAL-REDACTION --execute-backend --execute-browser
```

Equivalent browser-only commands:

```bash
node tests/e2e/phase3_real_activity_browser.mjs --gate P3-REAL-ACTIVITY-READ
node tests/e2e/phase3_real_activity_browser.mjs --gate P3-REAL-ACTIVITY-ACTION
node tests/e2e/phase3_real_activity_browser.mjs --gate P3-REAL-LIVE-VISIBILITY
node tests/e2e/phase3_real_activity_browser.mjs --gate P3-REAL-REDACTION
```

Expected observations:

- READ: a real `capability.started` event, safe model/capability descriptor where available, activity
  UI distinct from the answer bubble.
- ACTION: preview, execution and verification stages from the unchanged host-controlled action
  lifecycle. `ODOO_AI_P3_ACTION_PROMPT` must target disposable reversible data.
- LIVE-VISIBILITY: the browser sees public activity while `/turn/status` is still non-terminal; the
  backend acceptance test independently proves a second DB connection sees the row before worker
  commit.
- REDACTION: no arbitrary payload, prompt, raw arguments/results, token/auth material, stdout/stderr
  or chain-of-thought.

## 7. Phase 4 real gates

Only count these after all four P3 gates have been recorded PASS on the same SHA.

```bash
node tests/e2e/phase4_real_answer_browser.mjs --gate P4-REAL-FIRST-DELTA
node tests/e2e/phase4_real_answer_browser.mjs --gate P4-REAL-FINAL-PARITY
node tests/e2e/phase4_real_answer_browser.mjs --gate P4-REAL-CANCEL-STREAM
node tests/e2e/phase4_real_answer_browser.mjs --gate P4-REAL-UTF8-FRAGMENT
```

The runner uses the actual panel to enqueue the turn, then observes the persisted live cursor from
the same authenticated browser session. It never manufactures token progress with a browser timer.

Expected observations:

- FIRST-DELTA: at least one real answer fragment is persisted before terminal completion;
  `agent.answer.started` exists and activity text is not concatenated into the answer.
- FINAL-PARITY: concatenated provisional answer equals the authoritative final response and the
  final rendered bubble contains one copy of that answer.
- CANCEL-STREAM: cancel after first answer fragment; no stale final response is appended later.
- UTF8-FRAGMENT: `España, pingüino, acción, ñ, 😀` survive provider/network fragmentation and final
  parity.

The provider adapter streams only the decoded `decision.answer` value from structured output. Raw
JSON, capability arguments, plan proposals and provider metadata are never forwarded as answer text.
The final validated `NextDecision` remains authoritative; provisional projection cannot authorize a
business effect.

## 8. HOOT

Run the complete addon HOOT suite and record its real totals:

```bash
# Use the project's existing Odoo/HOOT invocation for the installed database.
# At minimum include all @odoo_ai_assistant tests, including:
# - assistant_stream_failure.test.js
# - assistant_live_stream_client.test.js
```

Focused filters from `PHASE23_REAL_VALIDATION_RUNBOOK.md` remain useful for P2.4. HOOT is regression
coverage, not a substitute for the real browser gates.

## 9. Evidence and cleanup

For every gate record:

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

If any gate fails, repair the smallest responsible layer, add deterministic regression coverage and
rerun that exact gate. A P2 failure freezes P3/P4 acceptance; a P3 failure freezes P4 acceptance.

Finally stop the disposable process, delete only the disposable DB/filestore/logs, restore the normal
Odoo service and require HTTP 200:

```bash
dropdb "$ODOO_AI_TEST_DB"
rm -rf "/path/to/odoo-data-dir/filestore/$ODOO_AI_TEST_DB"
rm -f /tmp/odoo-ai-phase2-*.log /tmp/odoo-ai-phase3-*.log /tmp/odoo-ai-phase4-*.log
sudo systemctl start odoo-server.service
curl --fail --silent --show-error http://127.0.0.1:8069/web/login >/dev/null
```

Never delete a non-disposable database or retain credentials/raw provider output as evidence.
