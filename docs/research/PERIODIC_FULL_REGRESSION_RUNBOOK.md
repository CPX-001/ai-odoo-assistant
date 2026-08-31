# Periodic full regression runbook

Date: 2026-08-31  
Status: **ACTIVE — expensive validation is periodic, not per slice**

This is the canonical broad current-product regression strategy for `ai-odoo-assistant`.

The repository normally uses focused risk-based tests while implementing. Broad regression is deliberately expensive and must **not** run after every implementation slice. Run it only when the user explicitly asks for a complete regression, at a chosen periodic checkpoint, or when a current authoritative gate explicitly requires it.

The Product Behavior Evals suite is a distinct user-visible/agentic layer. Its first baseline is currently a dedicated pre-live-P7 gate governed by `PRODUCT_BEHAVIOR_EVALS_V1.md`; after that baseline is accepted, its SMOKE/FULL selections become part of periodic product regression as described below.

## 1. Acceptance rule

A periodic full regression is one coherent validation event against one exact candidate SHA.

It consists of:

```text
A. repository/static + current dependency-light contracts
B. complete Odoo addon regression
C. complete @odoo_ai_assistant HOOT/browser suite
D. permanent high-value real Odoo/provider/browser smoke + pending named real gates
E. Product Behavior Evals periodic selection when the product-eval harness has been accepted
F. one consolidated evidence record
```

Do not mark a stage PASS unless it was actually executed. Missing environment means `BLOCKED`, not PASS.

Historical sidecar/installer/milestone tests are not part of the current-product full regression unless the candidate intentionally changes that preserved lineage. See `tests/AGENTS.md`.

## 2. Required environment

Use a disposable Odoo 18 Community database and the exact candidate commit.

Typical environment variables from the accepted local harnesses include equivalents of:

```text
ODOO_BIN
ODOO_CONF
ODOO_AI_ADDONS_PATH
ODOO_AI_BASE_URL
ODOO_AI_DB
ODOO_AI_LOGIN
ODOO_AI_PASSWORD
```

Real provider scenarios require the installation's configured primary Codex App Server session. Browser gates require the accepted Chromium/Chrome headless Odoo test environment.

Do not store credentials, customer payloads, raw provider stdout/stderr, prompts, tool arguments/results containing business data, or private reasoning in evidence.

## 3. Stage A — full current dependency-light/static regression

Run from repository root, adapting only for the current environment/interpreter:

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

As the embedded-product inventory grows, add new current contract/eval files here. Do not silently pull legacy sidecar E2E scripts into this gate.

Gate ID:

```text
PERIODIC-FULL-DETERMINISTIC
```

Record exact test/assertion totals and failures.

## 4. Stage B — complete Odoo addon regression

Update/install the exact candidate and execute the entire addon test tag:

```bash
"$ODOO_BIN" -c "$ODOO_CONF" -d "$ODOO_AI_DB" \
  --addons-path="$ODOO_AI_ADDONS_PATH" \
  -u odoo_ai_assistant \
  --test-enable --test-tags '/odoo_ai_assistant' \
  --stop-after-init --log-level=test
```

This is the broad backend integration gate. It covers accumulated Odoo model/runtime/capability/ACL/queue/effect/approval/recovery regressions rather than repeatedly rerunning the entire addon after each small change.

Gate ID:

```text
PERIODIC-FULL-ODOO-ADDON
```

Record selected/total test count, failures and errors against the exact SHA.

## 5. Stage C — complete HOOT/browser regression

Run the complete `@odoo_ai_assistant` HOOT suite using `/web/tests` or the already accepted headless runner in the disposable environment.

The full suite is required here, not just touched files. It includes panel/multichat ownership, model/autonomy/planning preferences, streaming projection, semantic activity, TaskPlan/replan presentation, approval/recovery, contextual navigation and public-reference contracts.

Use loopback `localhost` for the headless browser when required by browser secure-context behavior, as established by accepted P5.8 evidence.

Gate ID:

```text
PERIODIC-FULL-HOOT
```

Record tests/assertions and the exact browser/Odoo candidate.

## 6. Stage D — real Odoo/Codex/product-path gates

Do **not** rerun every historical real gate automatically. Run:

1. the permanent high-value smoke scenarios below; and
2. every currently pending named real gate accumulated since the last accepted periodic checkpoint.

Permanent smoke coverage:

```text
authenticated basic chat/read
ACL or unavailable-capability fail-closed case
one preview/approval/write/verify path with disposable data
Stop/correction on an active turn
reconnect/replay without duplicate final/activity state
one contextual reference with fresh Odoo revalidation
current real provisional answer-streaming smoke once Product Behavior v1 has supplied its accepted runner
```

Phase 6 has no remaining real validation debt; its six named gates passed in the 2026-08-31 final regression. Future P7/P8/etc. real gates are added here only when their corresponding implementation exists and `EXECUTION_STATE.md` marks them pending.

Gate ID for the consolidated real batch:

```text
PERIODIC-FULL-REAL-PRODUCT
```

The evidence record must list every current named real gate individually as `PASS|FAIL|BLOCKED|NOT_APPLICABLE`.

### Recovery/effect observation rule

When later changes touch recovery semantics, preserve the same evidence quality established by Phase 6: distinguish transactional rollback, completed segmented units and uncertain external/in-flight effects; never infer safety from a provider/browser error alone.

## 7. Stage E — Product Behavior Evals

The permanent user-visible eval contract is `PRODUCT_BEHAVIOR_EVALS_V1.md`.

### First baseline

The first Product Behavior FULL is **not merely another Stage-E periodic run**. It is the active dedicated pre-live-P7 gate and must follow `PRODUCT_BEHAVIOR_EVALS_CODEX_HANDOFF.md`:

```text
SMOKE 12–15 scenarios / 1 trial
repair every HARD failure
FULL 50+ scenarios / 3 probabilistic trials
record baseline + timing distributions
freeze promotion thresholds from evidence
```

### After first acceptance

At ordinary important runtime/agent/UX checkpoints:

```text
PRODUCT-BEHAVIOR-SMOKE
```

is the default product-level regression layer.

At phase acceptance or selected periodic full-product checkpoints, run:

```text
PRODUCT-BEHAVIOR-FULL
```

with the current accepted repetition policy.

Product Behavior results must include separate provider/capability/preview/verification timing and streaming first-delta/final timing. A high semantic score cannot mask a HARD failure such as unauthorized write, Direct TaskPlan, duplicate effect/final answer, ungrounded installation fact or ACL leak.

Do not require exact hidden tool sequences where several safe solutions are valid.

## 8. Failure handling

If Stage A fails, repair before spending expensive Odoo/Codex/browser quota unless the failure itself requires that environment to diagnose.

If Stage B or C fails, preserve the first reproducible failure and avoid repeatedly rerunning the entire battery while repairing. Use focused reproduction until green, then rerun the affected broad stage once.

If a real/product behavior gate fails, create one coherent repair scope for the underlying contract. Do not split each symptom into tiny roadmap slices.

A failed periodic regression does not erase previously accepted historical evidence; it means the current candidate cannot be called fully regression-green.

## 9. Evidence format

Create one consolidated file under:

```text
docs/research/evidence/regression/YYYY-MM-DD/FULL-REGRESSION-<shortsha>.md
```

Minimum content:

```text
TESTED_SHA
Odoo version
Codex/App Server version or sanitized provider identity
model + reasoning effort where relevant
browser runner/version
PERIODIC-FULL-DETERMINISTIC   PASS|FAIL|BLOCKED
PERIODIC-FULL-ODOO-ADDON      PASS|FAIL|BLOCKED
PERIODIC-FULL-HOOT            PASS|FAIL|BLOCKED
PERIODIC-FULL-REAL-PRODUCT    PASS|FAIL|BLOCKED
PRODUCT-BEHAVIOR-SMOKE/FULL   PASS|FAIL|BLOCKED|NOT_APPLICABLE
individual current named real gates
product behavior hard-failure summary
provider/capability timing summary when product evals run
streaming first-delta/final summary when product evals run
exact commands/selectors
actual test/assertion/scenario/trial totals
sanitized failure codes/observations
```

Only after all stages required for that candidate are green may the evidence say `FULL_REGRESSION: PASS`.

## 10. Development between periodic regressions

Between full runs:

```text
implement coherent product work
 -> add/update technical tests and product eval scenarios where behavior changes
 -> run cheap focused tests for touched contracts when practical
 -> run Product Behavior SMOKE after important agent/runtime/UX changes once the harness is accepted
 -> record broader real/regression work as pending validation debt
 -> continue implementation unless a concrete authority/recovery/product HARD uncertainty makes further work unsafe
 -> batch accumulated broad debt into the next periodic full regression
```

Implementation progress does not have to consume a complete real-environment regression after every slice. Phase completion, safety claims and explicitly gated product behavior still require their applicable evidence.
