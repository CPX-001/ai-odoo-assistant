# Final full regression — Phase 6

Date: 2026-08-31
Scope: canonical current-product periodic regression, including all accumulated Phase-6 real gates

## Lineage and environment

```text
BASE_SHA: fc022a682904bc886526aed86d085a1b5aca4c7b
TESTED_SHA: fc022a682904bc886526aed86d085a1b5aca4c7b
FINAL_SHA: evidence publication commit (resolve with git log -1 -- this file)
Odoo: 18.0 Community
Provider: Codex App Server / codex-cli 0.144.2, authenticated ChatGPT session
Browser: Playwright 1.57.0 / bundled Chromium revision 1208
Database: disposable odoo_ai_p6_final_20260831
```

The run started from a clean, freshly pulled `main` at `BASE_SHA`. Product code did not change
during validation. The publication checkpoint adds only the durable final real-gate runner,
this evidence, and current execution state.

## Result matrix

| Gate | Result | Actual evidence |
|---|---|---|
| PERIODIC-FULL-DETERMINISTIC | PASS | 246 unit tests; 39 current E2E contracts; 14 + 12 JavaScript assertions; compile/static checks green |
| PERIODIC-FULL-ODOO-ADDON | PASS | 281 Odoo-counted tests / 205 test methods; 0 failures, 0 errors |
| PERIODIC-FULL-HOOT | PASS | 157 tests / 604 assertions |
| PERIODIC-FULL-REAL-PRODUCT | PASS | all permanent smokes and all six accumulated P6 real gates below |
| P6-REAL-MULTISTEP | PASS | 2 ordered typed effects; preview/approval/revalidation/execution/verification; no duplicates |
| P6-REAL-REPLAN | PASS | initial revision 1; host evidence; progress revision 2; structural replan revision 3 |
| P6-REAL-EFFECT-ATOMICITY | PASS | 2 Odoo-local steps rolled back together after injected pre-commit failure |
| P6-REAL-SEGMENTED-RECOVERY | PASS | completed unit durable; in-flight external unit uncertain; fresh worker blocked blind replay |
| P6-REAL-LOOP-BOUNDS | PASS | 8-call ceiling, 5-effect ceiling, provider-decision exhaustion, host counter non-evasion |
| P6-REAL-EFFECT-JOURNAL | PASS | patch/create/delete classification, hidden raw payloads, TTL, target metadata and compensation |

```text
FULL_REGRESSION: PASS
PHASE_6: COMPLETE
```

## Stage A — deterministic/static

Commands actually executed:

```bash
git status --short
git rev-parse HEAD
git diff --check
.venv/bin/python -m compileall -q addons/odoo_ai_assistant tests
.venv/bin/python -m pytest -q tests/unit
.venv/bin/python -m pytest -q \
  tests/e2e/test_next_decision_contract.py \
  tests/e2e/test_canonical_plan_proposal.py \
  tests/e2e/test_phase6_planning_contract.py \
  tests/e2e/test_phase6_adaptive_planning_contract.py \
  tests/e2e/test_phase6_effect_recovery_contract.py \
  tests/e2e/test_e2e_decision_sequences.py
node tests/js/failure_contract_test.mjs
node tests/js/public_activity_contract_test.mjs
```

Results:

```text
tests/unit: 246 passed in 1.32s
current E2E selection: 39 passed in 0.11s
failure_contract_test.mjs: 14 assertions PASS
public_activity_contract_test.mjs: 12 assertions PASS
compileall / git diff --check: PASS
```

The runbook's literal `python3 -m pytest` first failed before collection because system Python had
no pytest. The repository `.venv/bin/python` was used as the harmless environment adaptation; no
test was counted from the failed invocation.

The added durable Stage-D runner was subsequently checked with:

```bash
.venv/bin/ruff check tests/e2e/p6_final_real_product_gate.py
.venv/bin/python -m py_compile tests/e2e/p6_final_real_product_gate.py
```

Result: PASS.

## Stage B — complete Odoo addon

Exact effective command:

```bash
sudo -u odoo /odoo/venv/bin/python3 /odoo/odoo-server/odoo-bin \
  --config=/etc/odoo-server.conf \
  --database=odoo_ai_p6_final_20260831 \
  --addons-path=/odoo/odoo-server/addons,/odoo/custom/addons/odoo-ai-assistant/addons \
  --init=odoo_ai_assistant --test-enable --test-tags=/odoo_ai_assistant \
  --stop-after-init --http-port=18096 --gevent-port=18097 \
  --logfile=/tmp/p6-final-full-odoo.log
```

Result from the Odoo log:

```text
odoo_ai_assistant: 281 tests 17.09s 13964 queries
0 failed, 0 errors of 205 tests
```

## Stage C — complete addon HOOT

Odoo was served from the exact candidate at `http://localhost:18096`. The accepted transformed
headless runner used the bundled Codex Playwright package and Chromium executable:

```text
C:\Users\Kiril\AppData\Local\OpenAI\Codex\runtimes\cua_node\415ffebf3d576e9b\bin\node_modules
C:\Users\Kiril\AppData\Local\ms-playwright\chromium-1208\chrome-win64\chrome.exe
ODOO_AI_HOOT_FILTER=@odoo_ai_assistant
node --input-type=commonjs -
```

The stdin runner was the accepted Odoo `/web/tests` Playwright collector with its ESM imports
mechanically replaced by `require(...)`; it selected only `@odoo_ai_assistant`.

Result:

```text
[HOOT] Passed 157 tests (604 assertions, total time 1s)
```

An initial `/web/tests?...&mod=odoo_ai_assistant` selector did not constrain the current Odoo
collector, selected unrelated core suites and timed out after 300 seconds with unrelated
`@html_editor` failures. It is preserved as a selector/environment adaptation failure and is not
counted. The explicit canonical addon filter above is the complete addon HOOT gate.

## Stage D — real product batch

The server command for provider-backed stages was:

```bash
sudo -u odoo env CODEX_HOME=/home/cpx/.codex \
  /odoo/venv/bin/python3 /odoo/odoo-server/odoo-bin \
  --config=/etc/odoo-server.conf --database=odoo_ai_p6_final_20260831 \
  --addons-path=/odoo/odoo-server/addons,/odoo/custom/addons/odoo-ai-assistant/addons \
  --http-port=18096 --gevent-port=18097 --workers=0 --max-cron-threads=2 \
  --logfile=/tmp/p6-final-real-server-2.log
```

The permanent approval/browser smokes actually executed the existing runners:

```text
tests/e2e/p5_4_final_ux_browser.mjs --gate P5-REAL-CHAT-BASIC
tests/e2e/p5_4_approval_browser.mjs (approve; partner 160; action 56)
tests/e2e/p5_6_continuity_browser.mjs
```

Observed results:

```json
{"gate":"P5-REAL-APPROVAL-UX","result":"OBSERVED_OK_NOT_AUTOMATIC_PASS","decision":"approve","dedicated_approval_state":true,"visible_plan_step_risk":true,"controls_bound_to_persisted_turn":true,"preference_change_preserved_turn":true,"preapproval_business_write":false,"fixture_restored":true}
{"gate":"P5-REAL-CONTINUITY","result":"OBSERVED_OK_NOT_AUTOMATIC_PASS","reconnect_follow_up":true,"exact_prior_token_recovered":true,"persisted_context_version":1,"current_message_excluded":true,"cross_conversation_isolation":true}
```

The basic-chat turn itself completed once, with one assistant message and one completed event. Its
historical P5 runner expected an always-visible settled activity card, which is no longer required
by the current lazy activity contract. The current runner therefore verified authenticated real
read plus replay idempotency directly.

The durable final runner command pattern for each provider-backed stage was:

```bash
sudo -u odoo env CODEX_HOME=/home/cpx/.codex P6_FINAL_REAL_STAGE=<stage> \
  /odoo/venv/bin/python3 /odoo/odoo-server/odoo-bin shell \
  --config=/etc/odoo-server.conf --database=odoo_ai_p6_final_20260831 \
  --addons-path=/odoo/odoo-server/addons,/odoo/custom/addons/odoo-ai-assistant/addons \
  --no-http < tests/e2e/p6_final_real_product_gate.py
```

Actually executed stages and sanitized results:

```json
{"stage":"read","result":"PASS","real_read_capability":true,"duplicate_final":false,"duplicate_completed_activity":false,"effective_user_su_false":true}
{"stage":"unavailable","result":"PASS","fail_closed":true,"write_barrier":false,"terminal_state":"completed"}
{"stage":"stop","result":"PASS","active_turn_cancelled":true}
{"stage":"redirect","result":"PASS","active_redirect_applied":true}
{"stage":"reference","result":"PASS","fresh_odoo_revalidation":true,"stale_target_failed_closed":true}
{"stage":"multistep","result":"PASS","effect_steps":2,"ordered_dependencies":true,"approval_revalidation_verification":true,"duplicate_effects":0,"provider_execution_authority":false}
{"stage":"replan","result":"PASS","initial_revision":1,"replan_revision":3,"host_evidence_before_replan":true,"progress_structure_preserved":true,"taskplan_non_executable":true,"private_reasoning_exposed":false}
{"stage":"loop_reasoning","result":"PASS","attempted_calls":8,"successful_calls":7,"clean_bounded_termination":true}
{"stage":"loop_effect","result":"PASS","accepted_effect_steps":5,"business_writes":0,"clean_bounded_termination":true}
```

The unavailable-model attempt was rejected by the host and exposed no configuration values. The
reasoning ceiling made eight calls: seven schema results and one allowlist rejection; the ninth was
not executed and the final answer reported that honestly. The effect ceiling prepared five steps,
performed no pre-approval writes, and the disposable plan was rejected.

The first complex replan attempt selected an invalid optional field and exhausted the 12-decision
budget while correcting itself. It terminated fail-closed with
`agent_provider_decision_budget_exceeded`, providing the real provider-decision-ceiling
observation. A schema-bounded aggregate version then completed the required initial -> progress ->
host evidence -> structural replan path. Focused host assertions inside the complete Stage-B addon
run cover correctable/consecutive failure limits and prove TaskPlan updates cannot reset or evade
those counters.

Recovery/journal commands actually executed:

```bash
P6_PHASE2_GATE=atomicity        odoo-bin shell ... < tests/e2e/p6_phase2_real_gate.py
P6_PHASE2_GATE=segmented_setup  odoo-bin shell ... < tests/e2e/p6_phase2_real_gate.py
P6_PHASE2_GATE=segmented_resume odoo-bin shell ... < tests/e2e/p6_phase2_real_gate.py
P6_PHASE2_GATE=journal          odoo-bin shell ... < tests/e2e/p6_phase2_real_gate.py
```

Results:

```json
{"gate":"P6-REAL-EFFECT-ATOMICITY","result":"PASS","steps":2,"recovery_mode":"odoo_atomic","all_business_writes_rolled_back":true,"effective_user_su_false":true}
{"gate":"P6-REAL-SEGMENTED-RECOVERY","result":"PASS","stage":"failure_persisted","completed_prior_unit":true,"inflight_external_state":"uncertain","future_unit_unexecuted":true}
{"gate":"P6-REAL-SEGMENTED-RECOVERY","result":"PASS","stage":"fresh_worker_resume","completed_unit_preserved":true,"future_unit_unexecuted":true,"blind_replay_blocked":true}
{"gate":"P6-REAL-EFFECT-JOURNAL","result":"PASS","classifications":["reversible","reconstructable","irreversible"],"raw_payloads_hidden":true,"retention_days":7,"target_metadata_present":true,"reversible_row_reverted":true,"reconstructable_not_presented_as_undo":true,"effective_user_su_false":true}
```

## Repairs and changes

- No product-semantics repair was required.
- Added `tests/e2e/p6_final_real_product_gate.py`, a disposable-database, persisted-turn runner for
  the permanent final smokes and the provider-backed P6 planning/budget gates.
- Adapted only the validation harness to current neutral capability/plan field names
  (`odoo.aggregate_records`, `binding_fingerprint`, `step_id`/`title`) and to count rejected calls
  as consumed reasoning budget.
- Added this evidence and advanced `docs/research/EXECUTION_STATE.md`.

All business fixtures were disposable. No credentials, raw provider streams, private reasoning or
customer payloads are stored in Git.
