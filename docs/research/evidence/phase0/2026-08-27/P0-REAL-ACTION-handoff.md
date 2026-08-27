# P0-REAL-ACTION — real-environment handoff

Date: 2026-08-27  
Inspected HEAD: `8c21be0671bfb8f7df158cf32e6f624c043f7de6`  
Validation ID: `P0-REAL-ACTION`  
Gate: `HARD`  
Status: `REAL_ENV_VALIDATION_REQUIRED`

## Why this remains a real gate

The current host-side implementation already revalidates capability version/binding, preview preconditions and current policy before crossing the durable write barrier. Approval requeues the same bound plan, effects execute under the effective Odoo user Environment (`su=False`), and verification follows execution. Deterministic repository tests cover preview/approve/execute/verify, rejection without writes, stale-precondition rejection and tampered-binding rejection.

Those tests do not prove the integrated browser -> Odoo -> cron -> Codex -> preview -> approval -> effect -> verification path on the current deployment. Phase 0 therefore remains open until the real product path is observed.

## Machine-report clarification

`tests/e2e/phase0_report.py` marks the minimum matrix `action=true` only when at least one accepted `capture_kind=live_http` scenario belongs to category `write`.

The Phase 0 catalog currently has:

```text
write_preview         category=write  entrypoint=enqueue        expected=awaiting_confirmation
write_execute_verify  category=write  entrypoint=plan_decision  expected=completed
```

`tests/e2e/phase0_live_capture.py` currently supports `entrypoint=enqueue` only. Therefore it can produce the machine-readable `write_preview` member required by the aggregate report, but it cannot itself drive the approval/execution scenario.

Do not weaken the gate to match the tooling. Closing Phase 0 requires **both**:

1. one authoritative browser `P0-REAL-ACTION` PASS through preview, explicit approval, exactly one effect and verification;
2. one sanitized accepted `write_preview` live capture so `phase0_report.py` can evaluate the write member of its machine matrix.

If the write-preview capture is a second turn, reject it after capture. Never approve it merely to make the report pass.

## 1. Authoritative browser ACTION procedure

Use only a disposable/demo partner and a harmless reversible field. Prefer a dedicated test user/partner. The effective Assistant policy must require confirmation for the chosen write (for example `always_confirm`); do not relax a stronger administrator/system restriction.

Before the turn record, without committing sensitive values:

```text
commit_tested: current main
odoo_version: 18.x
codex_version: actual configured version
user_profile: disposable internal user
service_identity: current Odoo PID/start identity or equivalent stability evidence
fixture: disposable res.partner id + field name
original_value_recorded: yes
```

Then:

1. Open the disposable partner in Odoo and the real Assistant panel.
2. Request exactly one reversible update to the chosen field.
3. Require the turn to reach `awaiting_confirmation`.
4. Inspect the preview and require that it identifies the exact partner, field, previous value and intended value.
5. Verify directly in Odoo that the field is still unchanged before approval.
6. Click the supported **Approve** action exactly once.
7. Wait for the normal plan-status flow; do not manually repeat the request or approval.
8. Require terminal completion, a completed verification result and the intended field value in Odoo.
9. Confirm the effect occurred exactly once, no `recovery_required`/ambiguous-write state appeared and Odoo remained healthy/stable.
10. Capture only sanitized evidence, then restore the disposable field to its original value outside the Assistant validation turn.

Immediate FAIL/stop conditions:

- preview missing or ambiguous;
- target/field/value does not match the intended reversible change;
- record changes before explicit approval;
- approval must be clicked more than once or a blind retry is needed;
- effect occurs zero times or more than once;
- verification fails or disagrees with Odoo;
- turn enters uncertain recovery after the write barrier;
- Odoo restarts or becomes unhealthy during the measured turn.

## 2. Machine-readable write-preview capture

After the authoritative ACTION has been evaluated and the fixture restored, create a **separate preview-only** capture for the aggregate report.

Set the normal Phase 0 environment variables. The message must request one harmless reversible update to the disposable partner and the screen should identify that partner. Example:

```bash
export ODOO_AI_PHASE0_DB='...'
export ODOO_AI_PHASE0_LOGIN='...'
export ODOO_AI_PHASE0_PASSWORD='...'
export ODOO_AI_PHASE0_MESSAGE='Prepare exactly one harmless reversible update on the disposable partner; do not claim it was executed.'
export ODOO_AI_PHASE0_SCREEN_JSON='{"model":"res.partner","res_id":<DISPOSABLE_PARTNER_ID>,"view_type":"form"}'

python tests/e2e/phase0_live_capture.py \
  --scenario write_preview \
  --out /tmp/phase0/write-preview-current.json
```

Require:

```text
exit status: 0
scenario_id: write_preview
capture_kind: live_http
expectation_met: true
final state: awaiting_confirmation
```

This capture must remain preview-only. Obtain its plan/turn id from the sanitized trace's `turn_persisted` timing entry and reject it through the normal plan-decision route:

```bash
export P0_PREVIEW_TRACE=/tmp/phase0/write-preview-current.json

python - <<'PY'
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, "tests/e2e")
from phase0_live_capture import OdooJsonClient

trace = json.loads(Path(os.environ["P0_PREVIEW_TRACE"]).read_text(encoding="utf-8"))
plan_id = next(
    item["turn_id"]
    for item in trace["timings"]
    if item.get("point") == "turn_persisted"
)
client = OdooJsonClient(
    os.environ.get("ODOO_AI_PHASE0_BASE_URL", "http://127.0.0.1:8069")
)
client.authenticate(
    db=os.environ["ODOO_AI_PHASE0_DB"],
    login=os.environ["ODOO_AI_PHASE0_LOGIN"],
    password=os.environ["ODOO_AI_PHASE0_PASSWORD"],
)
result = client.call(
    "/odoo_ai/v1/turn/plan-decision",
    {"plan_id": plan_id, "decision": "reject"},
)
if (
    not isinstance(result, dict)
    or result.get("ok") is not True
    or result.get("state") != "rejected"
):
    raise SystemExit("preview cleanup failed")
print("preview rejected without execution")
PY
```

Verify the disposable record remains unchanged after rejecting this second preview.

## 3. Aggregate Phase 0 report

Pass only actual Phase 0 live-capture JSON objects to the report; the evidence directory also contains other JSON artifacts that are not captures. One safe way to select them is:

```bash
mapfile -t P0_CAPTURES < <(
python - <<'PY'
import json
from pathlib import Path

root = Path("docs/research/evidence/phase0/2026-08-27")
for path in sorted(root.glob("*.json")):
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        continue
    if (
        isinstance(value, dict)
        and value.get("capture_kind") == "live_http"
        and isinstance(value.get("scenario_id"), str)
    ):
        print(path)
print("/tmp/phase0/write-preview-current.json")
PY
)

python tests/e2e/phase0_report.py \
  "${P0_CAPTURES[@]}" \
  --out /tmp/phase0/report-current.json
```

Phase 0 closes only when:

```text
P0-REAL-ACTION browser validation: PASS
phase0_report.py exit status: 0
ready_for_phase1: true
minimum_live_matrix: true
five_failure_pairs: true
```

The preview-only capture satisfies the aggregate report's machine write-member requirement; the browser ACTION proves actual approval/execution/verification. Neither substitutes for the other.

## 4. Evidence to publish

Record a sanitized note/artifact with at least:

```text
validation_id: P0-REAL-ACTION
commit_tested:
date:
odoo_version:
codex_version:
user_profile:
result: PASS | FAIL
preview_observed: true | false
explicit_approval_observed: true | false
effect_count: 0 | 1 | >1 | unknown
verification_result: PASS | FAIL | unknown
odoo_service_stable: true | false
fixture_restored: true | false
phase0_report_exit:
ready_for_phase1:
artifact_refs:
notes:
```

Never publish the password, prompt text containing sensitive data, raw provider output, raw tool arguments/results, private reasoning, or unrestricted customer data.
