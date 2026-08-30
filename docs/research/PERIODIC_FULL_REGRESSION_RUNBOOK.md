# Periodic full regression runbook

Date: 2026-08-30  
Status: **ACTIVE — expensive validation is periodic, not per slice**

This is the canonical full current-product regression for `ai-odoo-assistant`.

The repository normally uses focused risk-based tests while implementing. This battery is deliberately expensive and must **not** run after every implementation slice. Run it only when the user explicitly asks for a complete regression, at a chosen periodic checkpoint, or when a current authoritative gate explicitly requires it.

The purpose is to batch accumulated validation debt into one execution window instead of repeatedly consuming the real Odoo/Codex/browser environment for small changes.

## 1. Acceptance rule

A periodic full regression is one coherent validation event against one exact candidate SHA.

It consists of:

```text
A. repository/static + current dependency-light contracts
B. complete Odoo addon regression
C. complete @odoo_ai_assistant HOOT/browser suite
D. all currently accumulated named real-product gates that are implementable on that SHA
E. one consolidated evidence record
```

Do not mark a stage PASS unless it was actually executed. Missing environment means `BLOCKED`, not PASS.

Historical sidecar/installer/milestone tests are not part of the current-product full regression unless the candidate intentionally changes that preserved lineage. See `tests/AGENTS.md`.

## 2. Required environment

Use a disposable Odoo 18 Community database and the exact candidate commit.

Typical environment from the accepted P5 harness:

```text
ODOO_BIN
ODOO_CONF
ODOO_AI_ADDONS_PATH
ODOO_AI_P5_BASE_URL
ODOO_AI_P5_DB
ODOO_AI_P5_LOGIN
ODOO_AI_P5_PASSWORD
```

Real provider scenarios require the installation's configured primary Codex App Server session. Browser gates require the accepted Chromium/Chrome headless Odoo test environment.

Do not store credentials, customer payloads, raw provider stdout/stderr, prompts or private reasoning in evidence.

## 3. Stage A — full current dependency-light/static regression

Run from repository root:

```bash
git status --short
git rev-parse HEAD
git diff --check
python -m compileall -q addons/odoo_ai_assistant tests
python -m pytest -q tests/unit
python -m pytest -q \
  tests/e2e/test_next_decision_contract.py \
  tests/e2e/test_canonical_plan_proposal.py \
  tests/e2e/test_phase6_planning_contract.py \
  tests/e2e/test_phase6_adaptive_planning_contract.py \
  tests/e2e/test_phase6_effect_recovery_contract.py \
  tests/e2e/test_e2e_decision_sequences.py
node tests/js/failure_contract_test.mjs
node tests/js/public_activity_contract_test.mjs
```

As the current embedded-product dependency-light inventory grows, add new current contract/eval files here. Do not silently pull legacy sidecar E2E scripts into this gate.

Gate ID:

```text
PERIODIC-FULL-DETERMINISTIC
```

Record exact test/assertion totals and failures.

## 4. Stage B — complete Odoo addon regression

Update/install the exact candidate and execute the entire addon test tag:

```bash
"$ODOO_BIN" -c "$ODOO_CONF" -d "$ODOO_AI_P5_DB" \
  --addons-path="$ODOO_AI_ADDONS_PATH" \
  -u odoo_ai_assistant \
  --test-enable --test-tags '/odoo_ai_assistant' \
  --stop-after-init --log-level=test
```

This is intentionally the broad backend integration gate. It covers the accumulated Odoo model/runtime/capability/ACL/queue/effect/approval/recovery regressions rather than repeatedly rerunning the entire addon after each small change. It includes the P6 planning preference/settings tests, `TestAssistantEffectJournal` and format-v3 recovery-unit assertions.

Gate ID:

```text
PERIODIC-FULL-ODOO-ADDON
```

Record selected/total test count, failures and errors against the exact SHA.

## 5. Stage C — complete HOOT/browser regression

Run the complete `@odoo_ai_assistant` HOOT suite using `/web/tests` or the already accepted headless runner in the disposable environment.

The full suite is required here, not just touched files. It includes panel, multi-chat ownership, model/autonomy/planning preferences, streaming, semantic activity, live TaskPlan/replan presentation, approval/recovery, contextual navigation and public-reference contracts.

Use loopback `localhost` for the headless browser when required by browser secure-context behavior, as established by accepted P5.8 evidence.

Gate ID:

```text
PERIODIC-FULL-HOOT
```

Record tests/assertions and the exact browser/Odoo candidate.

## 6. Stage D — accumulated real Odoo/Codex/product-path gates

Do **not** rerun every historical real gate automatically. Run:

1. the permanent high-value smoke scenarios below; and
2. every currently pending named real gate accumulated since the last accepted periodic/full checkpoint.

Permanent smoke coverage:

```text
authenticated basic chat/read
ACL or unavailable-capability fail-closed case
one preview/approval/write/verify path with disposable data
Stop/correction on an active turn
reconnect/replay without duplicate final/activity state
one contextual reference with fresh Odoo revalidation
```

Current accumulated Phase-6 real debt:

```text
P6-REAL-MULTISTEP
P6-REAL-REPLAN
P6-REAL-EFFECT-ATOMICITY
P6-REAL-SEGMENTED-RECOVERY
P6-REAL-LOOP-BOUNDS
P6-REAL-EFFECT-JOURNAL
```

A gate is included only when the corresponding implementation exists and its scenario can honestly be exercised. Unimplemented future-phase gates remain roadmap work, not test failures.

### Planning/replan observation

For `P6-REAL-REPLAN`, use a complex safe task whose first TaskPlan assumption is invalidated by a real Odoo read/evidence result. Verify that the next TaskPlan revision is structural only after that evidence, has a bounded public replan summary, remains separate from EffectPlan authority and updates visibly without exposing private reasoning. Also verify that the same TaskPlan cannot structurally rewrite itself as an ordinary `progress` update.

### Recovery-specific observations

For `P6-REAL-EFFECT-ATOMICITY`, verify that a 2-5 step Odoo-local `odoo_atomic` recovery unit really rolls back together when a disposable injected failure occurs before transaction completion.

For `P6-REAL-SEGMENTED-RECOVERY`, use a trusted disposable/test capability declaring a segmented or external recovery mode. Verify that a completed prior unit remains durably distinguishable, the in-flight unit is `rolled_back` or `uncertain` according to its mode, future units remain unexecuted, and restarting the worker never blindly replays the persisted in-flight unit.

For `P6-REAL-EFFECT-JOURNAL`, inspect patch/create/delete journal entries through the owned-turn host surface. Verify retention/classification/target metadata, confirm raw before/after/receipt snapshots are not exposed through the normal user projection, and verify a supported compensation moves reversible rows to `reverted`. `reconstructable` must never be presented as a full undo guarantee.

Gate ID for the consolidated real batch:

```text
PERIODIC-FULL-REAL-PRODUCT
```

The evidence record must still list every named gate individually as PASS/FAIL/BLOCKED/NOT_APPLICABLE.

## 7. Failure handling

If Stage A fails, repair before spending the expensive Odoo/Codex/browser quota unless the failure itself requires that environment to diagnose.

If Stage B or C fails, preserve the first reproducible failure and avoid repeatedly rerunning the entire battery while repairing. Use focused reproduction until green, then rerun the affected broad stage once.

If a real gate fails, create one coherent repair scope for the underlying contract. Do not split each symptom into tiny roadmap slices.

A failed periodic regression does not erase previously accepted historical evidence; it means the current candidate cannot be called fully regression-green.

## 8. Evidence format

Create one file under:

```text
docs/research/evidence/regression/YYYY-MM-DD/FULL-REGRESSION-<shortsha>.md
```

Minimum content:

```text
TESTED_SHA
Odoo version
Codex/App Server version or sanitized provider identity
browser runner/version
PERIODIC-FULL-DETERMINISTIC   PASS|FAIL|BLOCKED
PERIODIC-FULL-ODOO-ADDON      PASS|FAIL|BLOCKED
PERIODIC-FULL-HOOT            PASS|FAIL|BLOCKED
PERIODIC-FULL-REAL-PRODUCT    PASS|FAIL|BLOCKED
individual current named real gates
exact commands
actual test/assertion totals
sanitized failure codes/observations
```

Only after all required stages for that candidate are green may the evidence say `FULL_REGRESSION: PASS`.

## 9. Development between periodic regressions

Between full runs:

```text
implement coherent product work
 -> add/update tests in the repository
 -> run cheap focused tests for touched contracts when practical
 -> record real/broad tests as pending validation debt
 -> continue implementation unless a concrete authority/recovery uncertainty makes further work unsafe
 -> batch the accumulated debt into the next periodic full regression
```

This means an implementation slice may be `IMPLEMENTED_PENDING_PERIODIC_VALIDATION` without pretending it is accepted. Phase completion and safety claims still require the applicable evidence; implementation progress does not have to consume a full real-environment regression after every slice.

At the current cursor all Phase-6 implementation blocks are present, so the next periodic run is a meaningful phase acceptance checkpoint rather than a per-slice regression.
