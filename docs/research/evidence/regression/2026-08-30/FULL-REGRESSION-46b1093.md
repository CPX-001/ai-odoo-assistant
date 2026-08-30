# Phase-6 periodic full regression — 46b1093

Date: 2026-08-30  
Result: **BLOCKED IN STAGE D**

## Candidate and environment

```text
TESTED_SHA: 46b109367a5d223cecbc0e9586d5d846b561afdd
base pulled from origin/main: 7f42e3926093c21d392636a7e50c0641d52c61d3
Odoo: 18.0 Community
Codex App Server: codex-cli 0.144.2, host-owned authenticated ChatGPT session
Browser: Chromium 140.0.7339.16 through Playwright 1.60.0
PostgreSQL: 16.15, disposable local cluster on loopback
database: disposable odoo_ai_p6_* databases
```

The candidate contains three focused repairs discovered during this run:

- `d8c410a`: allow empty prepared EffectJournal after/receipt payloads without violating SQL
  `NOT NULL` semantics;
- `69ae935`: make the planning picker template extension independent of the earlier send-button
  type replacement in minified asset order;
- `46b1093`: reject no-op TaskPlan `progress` revisions as correctable provider errors instead of
  publishing fictitious progress until the provider-decision budget is exhausted.

No customer data, credentials, provider output, prompts or private reasoning are retained here.

## Consolidated result

```text
PERIODIC-FULL-DETERMINISTIC   PASS
PERIODIC-FULL-ODOO-ADDON      PASS
PERIODIC-FULL-HOOT            PASS
PERIODIC-FULL-REAL-PRODUCT    BLOCKED
FULL_REGRESSION               BLOCKED
```

Phase 6 is not accepted and Phase 7 is not eligible while Stage D remains blocked.

## Stage A — deterministic contracts

Executed against `46b1093`:

```bash
/tmp/odoo-ai-p6-service-venv/bin/python -m compileall -q addons/odoo_ai_assistant tests
/tmp/odoo-ai-p6-service-venv/bin/python -m pytest -q tests/unit
/tmp/odoo-ai-p6-service-venv/bin/python -m pytest -q \
  tests/e2e/test_next_decision_contract.py \
  tests/e2e/test_canonical_plan_proposal.py \
  tests/e2e/test_phase6_planning_contract.py \
  tests/e2e/test_phase6_adaptive_planning_contract.py \
  tests/e2e/test_phase6_effect_recovery_contract.py \
  tests/e2e/test_e2e_decision_sequences.py
node tests/js/failure_contract_test.mjs
node tests/js/public_activity_contract_test.mjs
```

Observed:

```text
compileall: PASS
tests/unit: 246 passed
current P6/E2E contracts: 35 passed
failure contract: 14 assertions passed
public activity contract: 12 assertions passed
git diff --check: PASS
```

An earlier invocation accidentally selected system Python and stopped during collection because
the legacy service package dependencies were absent. It executed no tests and is excluded from the
gate result; the complete command was immediately repeated with the prepared isolated service
virtualenv above.

## Stage B — complete Odoo addon

Executed with the disposable PostgreSQL cluster and the complete addon tag:

```bash
"$ODOO_BIN" -d "$ODOO_AI_P6_BACKEND_DB" \
  --db_host=127.0.0.1 --db_port="$ODOO_AI_P6_DB_PORT" --db_user="$ODOO_AI_P6_DB_USER" \
  --addons-path="$ODOO_AI_ADDONS_PATH" -u odoo_ai_assistant \
  --test-enable --test-tags=/odoo_ai_assistant --stop-after-init --log-level=test
```

Observed:

```text
odoo_ai_assistant test statistics: 265 tests
selected unittest methods: 193
failures: 0
errors: 0
```

The count includes the new no-op TaskPlan convergence regression.

## Stage C — complete addon HOOT suite

Executed through the accepted headless runner with:

```text
ODOO_AI_HOOT_FILTER=@odoo_ai_assistant
assets: production/minified path
browser origin: loopback
```

Observed:

```text
152 tests passed
588 assertions passed
0 failures
```

## Stage D — real product path

Before the final candidate, the permanent effect smoke reproduced a real convergence defect: the
provider emitted repeated TaskPlan `progress` revisions without changing any step state. The host
eventually failed with `agent_provider_decision_budget_exceeded`, before the write barrier. That
failure produced the focused repair in `46b1093` and its deterministic/Odoo regressions.

The smoke was then retried on exact candidate `46b1093`. Odoo authenticated successfully and
created the durable turn, but the configured host Codex session rejected every attempt before its
first decision:

```text
normalized error: codex_turn_failed
provider category: provider_capacity
provider code: usageLimitExceeded
effect state: none
write barrier: false
attempts: 3
```

The disposable business fixture was removed through Odoo after the blocked run. This provider
capacity condition prevents honest observation of every real-provider gate; it is not counted as a
product PASS or product FAIL.

```text
authenticated basic chat/read              BLOCKED — usageLimitExceeded
ACL/unavailable capability fail-closed      BLOCKED — usageLimitExceeded
preview/approval/write/verify               BLOCKED — usageLimitExceeded before proposal
Stop/correction                             BLOCKED — usageLimitExceeded
reconnect/replay                            BLOCKED — usageLimitExceeded
contextual reference revalidation           BLOCKED — usageLimitExceeded

P6-REAL-MULTISTEP                           BLOCKED — usageLimitExceeded
P6-REAL-REPLAN                              BLOCKED — usageLimitExceeded
P6-REAL-EFFECT-ATOMICITY                    BLOCKED — usageLimitExceeded
P6-REAL-SEGMENTED-RECOVERY                  BLOCKED — usageLimitExceeded
P6-REAL-LOOP-BOUNDS                         BLOCKED — usageLimitExceeded
P6-REAL-EFFECT-JOURNAL                      BLOCKED — usageLimitExceeded
```

## Continuation rule

Restore provider capacity without changing the candidate, then run Stage D on the exact
`46b1093` product lineage. If Stage D exposes another product defect, repair it with focused tests
and rerun the affected broad stages according to the periodic runbook. Only a fully green Stage D
may turn this evidence into Phase-6 acceptance and unlock Phase 7.
