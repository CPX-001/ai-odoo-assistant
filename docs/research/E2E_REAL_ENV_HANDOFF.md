# E2E real-environment validation handoff

Date: 2026-08-27  
Status: `REAL_ENV_VALIDATION_PASSED`<br>
Implementation/test SHA materially validated: `9f832af4d6b1e6b74659bcd30aab21db481fd4b9`

This document records the completed exact-tree validation and remains the rerun procedure. E2E-0
through E2E-4, the final automated battery, the App Server output-schema correction and the
turn/event transaction correction are implemented at the SHA above. HELLO, READ and the
authoritative browser ACTION all passed in a fresh disposable Odoo database. The commit containing
this document is a docs-only descendant of the implementation/test SHA.

This SHA supersedes `ee723a7d715970681ef1addffebcceb54dbd2027` after its real HELLO failed
before the first `assistant_decision`. The observed App Server 0.149.1 event was an HTTP 400
`invalid_json_schema` because the one-decision `outputSchema` used root `oneOf`; the adapter had
reduced it to `codex_turn_failed`. The replacement uses an App Server-compatible wire envelope and
keeps the sanitized diagnostic `codex_output_schema_invalid`. That adapter-only replacement did
not change host behavior; the later `9f832af` checkpoint contains the separate bounded transaction
correction described below.

## Latest exact-tree result

The adapter correction passed its real boundary. The follow-up correction commits reasoning
checkpoints and the ACTION pre-effect barrier on the primary worker cursor, removing the competing
update of `odoo_ai_turn` that previously caused:

```text
independent event append updates odoo_ai_turn.last_event_sequence
  -> active primary turn cursor flush/commit
  -> psycopg2.errors.SerializationFailure: concurrent update
```

At `9f832af`, standalone suites passed, the focused Odoo checkpoint regression passed, and the
combined selected Odoo queue/runtime/convergence/PLAN/adapter/capability/action suites completed 38
tests with zero failures or errors. Real HELLO completed on its first claim. Real READ completed
after one bounded model correction with no runtime/database retry. The strict browser ACTION reached
an exact canonical preview with the record unchanged, accepted one approval click, crossed one
barrier/effect, verified the result and completed without recovery. The aggregate Phase 0 report
returned `ready_for_phase1=true`. The disposable database was removed and Odoo was left active.

The sanitized PASS evidence is
`docs/research/evidence/phase0/2026-08-27/E2E-REAL-ENV-result-9f832af.md`. The earlier `e9420ae`
record remains the historical failure evidence for the corrected collision.

## 1. What is already automated

The final battery covers hello, READ, multi-read, patch, create, repairable errors, access denied, unsupported action, restart/idempotency, approval, exactly-once and verification across three test surfaces:

- `tests/e2e/test_e2e_convergence_battery.py`: dependency-light 12-case contract/regression battery;
- `addons/odoo_ai_assistant/tests/test_e2e_convergence_battery.py`: executable Odoo `TransactionCase` battery using the real `AgentTurnService`, capability registry/executor and real `res.partner` plan lifecycle;
- `addons/odoo_ai_assistant/tests/test_canonical_plan_host_loop.py`: focused canonical patch/create stage-only, approval, barrier and verification coverage.
- `addons/odoo_ai_assistant/tests/test_codex_decision_adapter.py`: App Server wire-schema, strict-envelope normalization and captured `invalid_json_schema` diagnostic regression.
- `addons/odoo_ai_assistant/tests/test_turn_queue.py`: real-cursor checkpoint/event ordering and stale-worker barrier/recovery coverage.

In the available connector environment the dependency-light final battery was executed from a reconstructed checkout mirror of the committed test/fixture/transcript and current asserted source boundaries:

```text
python tests/e2e/test_e2e_convergence_battery.py
............
Ran 12 tests
OK
```

At `9f832af`, these standalone contracts and the selected 38-test Odoo suite passed before the real
product-path validation. The supported Odoo worker/account HELLO, READ and strict browser ACTION
remain the authoritative checks for future behavior-changing replacements.

## 2. Exact checkout and standalone commands

Use a dedicated/disposable validation host. The repository installed by `installer/odoo18_install.sh` normally lives at `/odoo/custom/addons/ai-odoo-assistant` and Odoo at `/odoo/odoo-server` with virtualenv `/odoo/venv`.

```bash
export E2E_SHA='9f832af4d6b1e6b74659bcd30aab21db481fd4b9'
export REPO='/odoo/custom/addons/ai-odoo-assistant'

sudo -u odoo git -C "$REPO" fetch origin main
sudo -u odoo git -C "$REPO" checkout --detach "$E2E_SHA"
test "$(sudo -u odoo git -C "$REPO" rev-parse HEAD)" = "$E2E_SHA"
test -z "$(sudo -u odoo git -C "$REPO" status --porcelain)"

cd "$REPO"
python3 tests/e2e/test_e2e_convergence_battery.py
python3 tests/e2e/test_e2e_decision_sequences.py
python3 tests/e2e/test_next_decision_contract.py
python3 tests/e2e/test_working_transcript_contract.py
python3 tests/e2e/test_canonical_plan_proposal.py
python3 -m py_compile \
  addons/odoo_ai_assistant/models/turn_working_transcript.py \
  addons/odoo_ai_assistant/models/embedded_runtime.py \
  addons/odoo_ai_assistant/models/embedded_runtime_host_loop.py \
  addons/odoo_ai_assistant/runtime/agent/codex_decision.py \
  addons/odoo_ai_assistant/tests/test_turn_queue.py \
  addons/odoo_ai_assistant/tests/test_codex_decision_adapter.py \
  addons/odoo_ai_assistant/tests/test_e2e_convergence_battery.py \
  addons/odoo_ai_assistant/tests/test_canonical_plan_host_loop.py
```

Standalone PASS requires every command to exit `0`. Any failure is a gate failure; do not continue to real writes until understood.

## 3. Disposable Odoo database, addon install/update and Odoo tests

The repository installer is a development fixture for Ubuntu 24.04/WSL2. If the host is not already provisioned, from the exact repository checkout run:

```bash
sudo bash installer/odoo18_install.sh
```

For an existing validation host use a new disposable database. Do not point these commands at a production/customer database.

```bash
export ODOO_PY='/odoo/venv/bin/python'
export ODOO_BIN='/odoo/odoo-server/odoo-bin'
export ODOO_CONF='/etc/odoo-server.conf'
export E2E_DB="odoo_ai_e2e_final_$(date +%Y%m%d_%H%M%S)"

sudo systemctl stop odoo.service
sudo -u odoo createdb "$E2E_DB"

# Fresh install.
sudo -u odoo "$ODOO_PY" "$ODOO_BIN" \
  -c "$ODOO_CONF" -d "$E2E_DB" \
  -i odoo_ai_assistant --without-demo=all --stop-after-init --no-http

# Explicit addon update, required by this handoff even after a fresh install.
sudo -u odoo "$ODOO_PY" "$ODOO_BIN" \
  -c "$ODOO_CONF" -d "$E2E_DB" \
  -u odoo_ai_assistant --stop-after-init --no-http

# Final executable convergence battery.
sudo -u odoo "$ODOO_PY" "$ODOO_BIN" \
  -c "$ODOO_CONF" -d "$E2E_DB" \
  -u odoo_ai_assistant --test-enable \
  --test-tags=/odoo_ai_assistant:TestE2EConvergenceBattery \
  --stop-after-init --no-http

# Focused canonical PLAN regression.
sudo -u odoo "$ODOO_PY" "$ODOO_BIN" \
  -c "$ODOO_CONF" -d "$E2E_DB" \
  -u odoo_ai_assistant --test-enable \
  --test-tags=/odoo_ai_assistant:TestCanonicalPlanHostLoop \
  --stop-after-init --no-http

# Exact App Server adapter regression, including the captured invalid-schema event.
sudo -u odoo "$ODOO_PY" "$ODOO_BIN" \
  -c "$ODOO_CONF" -d "$E2E_DB" \
  -u odoo_ai_assistant --test-enable \
  --test-tags=/odoo_ai_assistant:TestCodexDecisionAdapter \
  --stop-after-init --no-http

# Turn/event checkpoint regression for the former PostgreSQL row collision.
sudo -u odoo "$ODOO_PY" "$ODOO_BIN" \
  -c "$ODOO_CONF" -d "$E2E_DB" \
  -u odoo_ai_assistant --test-enable \
  --test-tags=/odoo_ai_assistant:TestAssistantTurnQueue.test_primary_cursor_commits_event_and_working_checkpoint_without_row_collision \
  --stop-after-init --no-http
```

Odoo-test PASS requires zero failed/error tests and process exit `0`. Preserve the complete test log outside Git, then publish only a sanitized summary.

## 4. Disposable fixtures

Use an installation-scoped Codex account that is already authenticated through the supported product flow. Provider credentials remain in provider-owned `CODEX_HOME`; never place access/refresh tokens in the database, shell history or evidence.

Create a dedicated internal user and disposable partner. Fixture setup may use an administrator Odoo shell because it is test-host setup, not Assistant execution authority. The Assistant turn itself must use the dedicated user's effective Environment with `su=False`.

Choose local-only values:

```bash
export E2E_LOGIN="e2e-agent-$(date +%s)@invalid.local"
read -rsp 'Disposable Odoo password: ' E2E_PASSWORD; echo
export E2E_PASSWORD
export E2E_MARKER="E2E-AI-$(date +%Y%m%d-%H%M%S)"
export E2E_ORIGINAL_PHONE='+34 600 000 001'
export E2E_TARGET_PHONE='+34 600 000 002'
```

Then create the fixtures and force confirmation on this disposable database:

```bash
sudo -u odoo env \
  E2E_LOGIN="$E2E_LOGIN" \
  E2E_PASSWORD="$E2E_PASSWORD" \
  E2E_MARKER="$E2E_MARKER" \
  E2E_ORIGINAL_PHONE="$E2E_ORIGINAL_PHONE" \
  "$ODOO_PY" "$ODOO_BIN" shell -c "$ODOO_CONF" -d "$E2E_DB" --no-http <<'PY'
import json
import os

company = env.company
login = os.environ['E2E_LOGIN']
password = os.environ['E2E_PASSWORD']
marker = os.environ['E2E_MARKER']
original = os.environ['E2E_ORIGINAL_PHONE']

groups = [
    env.ref('base.group_user').id,
    env.ref('base.group_partner_manager').id,
]
user = env['res.users'].create({
    'name': 'E2E Assistant User',
    'login': login,
    'password': password,
    'company_id': company.id,
    'company_ids': [(6, 0, [company.id])],
    'groups_id': [(6, 0, groups)],
})
partner = env['res.partner'].create({
    'name': marker,
    'phone': original,
    'company_id': company.id,
})
icp = env['ir.config_parameter'].sudo()
icp.set_param('odoo_ai_assistant.agent_confirmation_mode', 'always_confirm')
icp.set_param('odoo_ai_assistant.agent_max_auto_risk', 'low')
icp.set_param('odoo_ai_assistant.codex_connection_enabled', 'true')
env.cr.commit()
print(json.dumps({'user_id': user.id, 'partner_id': partner.id, 'marker': marker}, sort_keys=True))
PY
```

Record the returned disposable `partner_id` locally:

```bash
export E2E_PARTNER_ID='<DISPOSABLE_PARTNER_ID>'
```

If the installation-scoped Codex account is not actually authenticated, stop here and connect it through the supported Settings/device-code flow. Setting the database enablement flag does not manufacture provider credentials.

Start Odoo for live HTTP/browser validation:

```bash
sudo systemctl start odoo.service
sudo systemctl is-active --quiet odoo.service
```

## 5. Real HELLO

Use the existing sanitized live-capture runner. It never stores the password, message, screen context, assistant answer, plan payload or raw tool/provider output.

```bash
mkdir -p /tmp/odoo-ai-e2e
export ODOO_AI_PHASE0_DB="$E2E_DB"
export ODOO_AI_PHASE0_LOGIN="$E2E_LOGIN"
export ODOO_AI_PHASE0_PASSWORD="$E2E_PASSWORD"
export ODOO_AI_PHASE0_MESSAGE='Reply with one short greeting.'
unset ODOO_AI_PHASE0_SCREEN_JSON

python3 tests/e2e/phase0_live_capture.py \
  --scenario hello \
  --out /tmp/odoo-ai-e2e/hello.json
```

HELLO PASS:

- command exit `0`;
- `capture_kind=live_http`;
- `expectation_met=true`;
- final turn state `completed`;
- no approval or write/recovery state;
- Odoo service remains healthy.

Any provider/account error, unexpected plan/approval, failed/cancelled/recovery state or service instability is FAIL.

## 6. Real READ

Use the same disposable partner and identify it in the screen hint. The text may mention only the disposable marker; never use customer data.

```bash
export ODOO_AI_PHASE0_MESSAGE="Find the disposable partner named ${E2E_MARKER} and report its phone."
export ODOO_AI_PHASE0_SCREEN_JSON="{\"model\":\"res.partner\",\"res_id\":${E2E_PARTNER_ID},\"view_type\":\"form\"}"

python3 tests/e2e/phase0_live_capture.py \
  --scenario read_partner \
  --out /tmp/odoo-ai-e2e/read-partner.json
```

READ PASS:

- exit `0`, `expectation_met=true`, final state `completed`;
- the visible browser answer matches the disposable fixture; record only `answer_matches_fixture=true`, not the raw answer;
- no record changes;
- no approval/write barrier/recovery state;
- at least one normal reasoning/tool activity boundary is observable and Odoo remains healthy.

A fabricated/mismatched answer, access bypass, mutation, approval prompt, terminal failure or instability is FAIL.

## 7. Real ACTION — authoritative browser path

This is the hard gate. Use the same disposable partner and the dedicated test user. Open the partner
form and the real Assistant panel. Before submitting, select the user-visible **Strict** autonomy
profile and verify that the picker displays **Estricto**. The user's stored autonomy profile is the
authoritative per-turn policy; prompt prose asking for confirmation does not override a permissive
profile, and the installation config parameter alone does not replace this browser check. Request
exactly one reversible change of `phone` from `E2E_ORIGINAL_PHONE` to `E2E_TARGET_PHONE`.

Required sequence:

1. the autonomy picker displays `Estricto` before submission;
2. the turn reaches `awaiting_confirmation`;
3. preview identifies the exact disposable partner, field, previous value and intended value;
4. directly verify in Odoo that the phone is still the original value before approval;
5. click the supported **Approve/Continuar** control exactly once;
6. do not repeat the request or approval;
7. wait for normal completion;
8. require the partner phone to equal the target value;
9. require verification to complete and no `recovery_required`/ambiguous-write state;
10. require Odoo service stability throughout.

Immediate ACTION FAIL/stop conditions:

- no canonical preview or wrong target/field/value;
- record changes before explicit approval;
- more than one approval click or blind retry is needed;
- effect occurs zero times or evidence indicates replay;
- verification fails/disagrees with Odoo;
- turn enters `failed`, `cancelled` or `recovery_required` after the effect barrier;
- Odoo restarts/becomes unhealthy.

After completion, collect **counts only** from Odoo; do not print working-item arguments/results:

```bash
sudo -u odoo env E2E_LOGIN="$E2E_LOGIN" "$ODOO_PY" "$ODOO_BIN" \
  shell -c "$ODOO_CONF" -d "$E2E_DB" --no-http <<'PY'
import json
import os
from collections import Counter

user = env['res.users'].search([('login', '=', os.environ['E2E_LOGIN'])], limit=1)
turn = env['odoo.ai.turn'].search([('user_id', '=', user.id)], order='id desc', limit=1)
events = env['odoo.ai.turn.event'].search([('turn_id', '=', turn.id)], order='sequence')
working = turn.working_items_payload or []
plan = turn.capability_plan_payload or {}
plan_payload = plan.get('plan') if isinstance(plan, dict) else {}
print(json.dumps({
    'turn_state': turn.state,
    'plan_state': plan_payload.get('state') if isinstance(plan_payload, dict) else None,
    'event_counts': dict(Counter(events.mapped('event_type'))),
    'working_kind_counts': dict(Counter(
        item.get('kind') for item in working if isinstance(item, dict) and isinstance(item.get('kind'), str)
    )),
}, sort_keys=True))
PY
```

For exactly-once/verification PASS require at minimum:

```text
turn_state = completed
plan_state = completed
execution.barrier event count = 1
verified_effect_receipt working-item count = 1
record unchanged before approval = true
approval clicks = 1
final partner phone = E2E_TARGET_PHONE
recovery.required event count = 0
```

The event/working-item count summary is supporting evidence; the authoritative result is the full observed browser/Odoo lifecycle plus direct record verification.

## 8. Optional machine-readable write-preview member

For the Phase 0 aggregate report, run a **separate preview-only** turn after restoring the field. Never approve this second turn.

```bash
export ODOO_AI_PHASE0_MESSAGE='Prepare exactly one harmless reversible phone update on the disposable partner; do not claim it was executed.'
export ODOO_AI_PHASE0_SCREEN_JSON="{\"model\":\"res.partner\",\"res_id\":${E2E_PARTNER_ID},\"view_type\":\"form\"}"

python3 tests/e2e/phase0_live_capture.py \
  --scenario write_preview \
  --out /tmp/odoo-ai-e2e/write-preview.json
```

PASS requires exit `0`, `expectation_met=true` and final state `awaiting_confirmation`. Reject that preview through the normal `/odoo_ai/v1/turn/plan-decision` route as documented in `docs/research/evidence/phase0/2026-08-27/P0-REAL-ACTION-handoff.md`; verify the record remains unchanged.

## 9. Sanitized evidence

Create a result note under a new date/SHA-specific evidence directory. Record booleans/counts and version/commit identity only. A minimal schema is:

```text
validation_id: E2E-REAL-ENV
implementation_test_sha: 9f832af4d6b1e6b74659bcd30aab21db481fd4b9
date:
odoo_version:
codex_version:
standalone_battery: PASS | FAIL
odoo_transaction_battery: PASS | FAIL
hello: PASS | FAIL
read: PASS | FAIL
read_answer_matches_fixture: true | false
action: PASS | FAIL
preview_observed: true | false
record_unchanged_before_approval: true | false
approval_clicks: 0 | 1 | >1
effect_barrier_count:
verified_effect_receipt_count:
verification_result: PASS | FAIL | unknown
recovery_required_observed: true | false
odoo_service_stable: true | false
fixture_cleaned: true | false
artifact_refs:
first_failure_boundary:
notes:
```

Allowed artifacts include the sanitized `phase0_live_capture.py` JSON traces, Odoo test summary, process exit codes and the count-only ACTION summary. Never publish passwords, tokens, raw prompts with sensitive data, raw provider output, raw capability arguments/results, private reasoning, unrestricted database rows or customer data.

On FAIL, preserve the first failing boundary and stop. Do not rerun writes blindly to obtain a PASS.

## 10. Cleanup

Restore the ACTION field before any second preview if the browser ACTION completed. At the end prefer dropping the entire disposable database:

```bash
sudo systemctl stop odoo.service
sudo -u odoo dropdb --if-exists "$E2E_DB"
sudo systemctl start odoo.service
sudo systemctl is-active --quiet odoo.service
unset E2E_PASSWORD ODOO_AI_PHASE0_PASSWORD
```

If the database must be retained temporarily for diagnosis, archive/remove only the disposable user/partner after preserving sanitized evidence and restore the temporary policy settings. Never reuse the disposable database as production data.

## Final gate

`REAL_ENV_VALIDATION_REQUIRED` is PASS for the implementation/test SHA above because it has:

1. standalone battery PASS;
2. Odoo `TransactionCase` battery PASS after addon update;
3. real HELLO PASS;
4. real READ PASS against disposable data;
5. real ACTION PASS through canonical preview, one explicit approval, exactly one barrier/effect, verification and no recovery ambiguity;
6. fixture cleanup and sanitized evidence recorded.

All six were observed at `9f832af`; the aggregate Phase 0 report also exited `0` with
`ready_for_phase1=true`. Future behavior-changing changes must rerun the affected sections rather
than inheriting this PASS automatically.
