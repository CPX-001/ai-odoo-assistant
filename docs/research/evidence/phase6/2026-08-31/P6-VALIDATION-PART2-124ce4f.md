# Phase 6 validation — Part 2

Date: 2026-08-31  
Scope: P6.4 and P6.6 recovery/journal gates only

## Lineage and environment

```text
BASE_SHA: fad24750bf3cefe9ad98a758c90c5bb6d6018135
TESTED_SHA: 124ce4f0583afde13e228f48e00362a5b35c1e58
FINAL_SHA: 124ce4f0583afde13e228f48e00362a5b35c1e58 (test/evidence candidate)
Odoo: 18.0 Community
Provider identity: Codex App Server / codex-cli 0.144.2 installed; not invoked by these provider-neutral recovery gates
Database: disposable odoo_ai_p6_part2_20260831
```

The evidence/state publication commit after `FINAL_SHA` changes documentation only. The Part-2
gate runner is `tests/e2e/p6_phase2_real_gate.py` and refuses databases whose names do not start
with `odoo_ai_`.

The run started from the published Part-1 checkpoint with:

```powershell
git checkout main
git pull --ff-only
git status --short
git rev-parse HEAD
```

The checkout was clean at `BASE_SHA`.

## Results

| Gate | Result | Evidence |
|---|---|---|
| P6.4 atomic vs segmented effects | PASS | Real atomic rollback and fresh-process segmented/external recovery |
| P6.6 EffectJournal | PASS | Real patch/create/delete journal projection, retention/classification, and compensation transition |
| P6-REAL-EFFECT-ATOMICITY | PASS | Two Odoo-local typed patches rolled back together after an injected pre-commit failure |
| P6-REAL-SEGMENTED-RECOVERY | PASS | Prior unit durable, external in-flight unit uncertain, future unit untouched, blind replay blocked after process restart |
| P6-REAL-EFFECT-JOURNAL | PASS | Raw snapshots hidden, target/classification/TTL present, reversible row moved to reverted |

There were no product failures or blocked Part-2 gates. Phase 6 is **not marked COMPLETE** because
the final applicable periodic regression remains unexecuted.

## Focused checks

Dependency-light recovery/journal contract:

```bash
python3 -m unittest -v tests.e2e.test_phase6_effect_recovery_contract
```

Result: **5 tests, PASS**.

Static checks:

```bash
python3 -m py_compile addons/odoo_ai_assistant/runtime/agent/plan.py addons/odoo_ai_assistant/models/effect_recovery_runtime.py addons/odoo_ai_assistant/models/effect_journal.py addons/odoo_ai_assistant/models/effect_journal_reversion.py
.venv/bin/ruff check tests/e2e/p6_phase2_real_gate.py
python3 -m py_compile tests/e2e/p6_phase2_real_gate.py
```

```powershell
git diff --check
```

Result: **PASS**.

Focused Odoo selection:

```powershell
wsl.exe -d Ubuntu-24.04 -u root -- sudo -u odoo /odoo/venv/bin/python3 /odoo/odoo-server/odoo-bin --config=/etc/odoo-server.conf --database=odoo_ai_p6_part2_20260831 --addons-path=/odoo/odoo-server/addons,/odoo/custom/addons/odoo-ai-assistant/addons --init=odoo_ai_assistant --test-enable --test-tags=/odoo_ai_assistant:TestAssistantEffectJournal,/odoo_ai_assistant:TestCanonicalPlanHostLoop,/odoo_ai_assistant:TestAssistantTurnControl,/odoo_ai_assistant:TestPhase2BrowserFailureProjection --stop-after-init --http-port=18094 --gevent-port=18095 --logfile=/tmp/p6-part2-focused-odoo.log
```

Result: **24 selected methods / 32 Odoo-counted tests, 0 failures, 0 errors**.

Focused HOOT selection:

```text
performed action card exposes revert only for host-declared available compensation
```

It ran through `tests/e2e/phase23_hoot_gate.mjs` against disposable Odoo, with the locally bundled
Playwright/Chromium runtime. Result: **1 test / 3 assertions, PASS**.

No complete dependency-light, addon, HOOT, historical P0-P5 or repository regression was run.
Part-1 tests and real gates were not repeated.

## Real gates

The exact command pattern for each runner stage was:

```bash
sudo -u odoo env P6_PHASE2_GATE=<stage> /odoo/venv/bin/python3 /odoo/odoo-server/odoo-bin shell --config=/etc/odoo-server.conf --database=odoo_ai_p6_part2_20260831 --addons-path=/odoo/odoo-server/addons,/odoo/custom/addons/odoo-ai-assistant/addons --no-http < /odoo/custom/addons/odoo-ai-assistant/tests/e2e/p6_phase2_real_gate.py
```

### P6-REAL-EFFECT-ATOMICITY — PASS

Stage: `P6_PHASE2_GATE=atomicity`.

```json
{"all_business_writes_rolled_back":true,"effective_user_su_false":true,"gate":"P6-REAL-EFFECT-ATOMICITY","injected_failure_before_commit":true,"recovery_mode":"odoo_atomic","result":"PASS","steps":2}
```

Two real `res.partner` patches executed and verified inside one `odoo_atomic` unit. A disposable
failure was raised after both writes but before transaction completion. A rollback and fresh read
showed both original values; neither partial write survived.

### P6-REAL-SEGMENTED-RECOVERY — PASS

Stages `segmented_setup` and `segmented_resume` ran in separate Odoo shell processes.

```json
{"completed_prior_unit":true,"future_unit_unexecuted":true,"gate":"P6-REAL-SEGMENTED-RECOVERY","inflight_external_state":"uncertain","result":"PASS","stage":"failure_persisted"}
{"blind_replay_blocked":true,"completed_unit_preserved":true,"future_unit_unexecuted":true,"gate":"P6-REAL-SEGMENTED-RECOVERY","result":"PASS","stage":"fresh_worker_resume"}
```

Trusted fixture capabilities declared host-owned `segmented` and `external` recovery metadata. The
first unit committed and remained verified. The injected external-unit failure persisted as
`uncertain`; its write and the future unit's write did not occur. A new Odoo process loaded the
persisted executing unit and failed closed with `capability_plan_recovery_required` before calling
any handler, proving that restart does not blindly replay it.

### P6-REAL-EFFECT-JOURNAL — PASS

Stage: `P6_PHASE2_GATE=journal`.

```json
{"classifications":["reversible","reconstructable","irreversible"],"effective_user_su_false":true,"gate":"P6-REAL-EFFECT-JOURNAL","raw_payloads_hidden":true,"reconstructable_not_presented_as_undo":true,"result":"PASS","retention_days":7,"reversible_row_reverted":true,"target_metadata_present":true}
```

Real patch/create/delete plans produced verified journal rows with conservative classifications,
recovery binding, target metadata and seven-day retention. The owned-turn user projection exposed
no before/after/receipt payload. Create was marked reconstructable but not reversible. Verified
host-only patch compensation restored the original value and changed the matching row to
`reverted`.

All business execution used the effective Odoo user Environment with `su=False`; superuser access
was confined to host-owned technical persistence and journal inspection inside the disposable
validation harness.

## Changes

- Added the reusable, fail-closed disposable Odoo-shell runner for the three Part-2 real gates.
- No product semantics were changed and no product repair was required.
- Removed all gate-created business records and turns. The disposable database and exact filestore
  were removed after recording results.

## Remaining acceptance work

```text
applicable final periodic regression from PERIODIC_FULL_REGRESSION_RUNBOOK.md
```

All six named Phase-6 real gates have now passed across the Part-1 and Part-2 evidence checkpoints,
but the unexecuted final periodic regression prevents a Phase-6 COMPLETE claim.
