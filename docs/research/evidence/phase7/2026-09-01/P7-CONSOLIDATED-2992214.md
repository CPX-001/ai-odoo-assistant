# Phase 7 consolidated validation checkpoint

Date: 2026-09-01
BASE_SHA: `2992214b3d54479fb71c57933c69c93618ff97b9`
TESTED_SHA: working tree based on BASE_SHA
FINAL_SHA: publication commit containing this evidence
Odoo: 18.0 Community
Provider: Codex App Server / `codex-cli 0.151.0-alpha.7.2`, current host-configured account only

## Result

```text
P7 IMPLEMENTATION COMPLETE / ACCEPTANCE BLOCKED PROVIDER CAPACITY
P8 NOT ELIGIBLE
```

All six Phase-7 real gates passed. Product Behavior SMOKE passed 15/15. The mandatory FULL x3 was
then executed until the current provider returned its sanitized `provider_usage_limit` blocker at
`PB-HOW-004`, trial 2. Exactly 76 of 162 trials completed, all 76 passed, and no HARD failure was
observed. The remaining 86 trials are unexecuted and are not PASS. The final periodic regression was
not started because the consolidated runbook permits it only after FULL is green.

| Gate | Result | Actual evidence |
|---|---|---|
| P7 deterministic/static | PASS | 26 pytest; scoped Ruff, compile, `git diff --check` PASS |
| Product Behavior focused | PASS | 53 pytest |
| Focused Odoo settings | PASS | 5 methods / 7 Odoo-counted tests |
| Installed fixture Odoo | PASS | 5 methods / 7 Odoo-counted tests; 0 failures/errors |
| Clean core install | PASS | `odoo_ai_assistant` installed on a fresh disposable DB |
| Focused HOOT | PASS | 10 tests / 32 assertions across the three required filters |
| Product Behavior SMOKE | PASS | 15/15, quality minimum/mean 100 |
| P7-REAL-PROVIDER-DISCOVERY | PASS | fixture appeared automatically; uninstall removed capabilities/Skills; core count 17 |
| P7-REAL-SELF-AWARENESS | PASS | base, configured admin and limited-user provider turns |
| P7-REAL-DISABLEMENT | PASS | disabled capability could not be called; re-enable recovered without restart hack |
| P7-REAL-CONTEXT-PROVIDER | PASS | bounded `res.partner` / form context reached reasoning as untrusted data |
| P7-REAL-DISCLOSURE | PASS | same `bulk.tool_119` selection; eager 120 tools 6152.448 ms, lazy 3 tools 5288.185 ms |
| P7-REAL-AUTHORITY | PASS | limited-user prompt override produced no admin PLAN call/effect; `su=False` |
| Product Behavior FULL x3 | BLOCKED | 76/162 PASS, 0 HARD failures; provider limit at PB-HOW-004 trial 2 |
| Final periodic regression | NOT EXECUTED | correctly not reached after FULL blocker |

## Preserved failures and repairs

1. The real Odoo registry initially did not discover the fixture provider (3 failures, 1 error of 5
   methods). Odoo 18 synthesizes registry classes; discovery now inspects the direct installed source
   classes in `_model_classes__`, with deterministic de-duplication and a focused regression.
2. The limited user could see the fixture's Settings-admin-only PLAN capability. The registry left
   configuration enablement `True` when `available_for()` denied a required group. Availability now
   combines both checks fail-closed; unit and real Odoo regressions pass.
3. SMOKE first reproduced PB-ACT-001 asking for optional person/company data instead of creating the
   named contact. Provider instructions now distinguish omitted optional contact fields from material
   ambiguity. The smallest rerun passed with one verified effect, then SMOKE passed 15/15.
4. The local Playwright package expected a browser revision not installed on the host. The HOOT gate
   accepts an explicit browser executable override; no product/browser semantics changed.
5. Added durable real-provider P7 gates for self-awareness, disablement/context/authority and the
   120-capability disclosure comparison. Shell gates explicitly publish Odoo cache invalidations to
   emulate the normal RPC request boundary.

## Commands actually executed

```text
git checkout main
git pull --ff-only
git status --short
git rev-parse HEAD

.venv/bin/python -m pytest -q tests/unit/test_capability_provider_extensions.py tests/unit/test_phase7_feature_negotiation.py tests/unit/test_phase7_extension_composition.py tests/unit/test_phase7_live_extension_context.py
.venv/bin/python -m pytest -q tests/product_behavior tests/unit/test_product_behavior_eval_harness.py tests/unit/test_provider_decision_timing.py tests/e2e/test_next_decision_contract.py tests/e2e/test_canonical_plan_proposal.py tests/e2e/test_phase6_planning_contract.py tests/e2e/test_phase6_adaptive_planning_contract.py tests/unit/test_answer_stream_contract.py
.venv/bin/python -m pytest -q tests/e2e/test_next_decision_contract.py tests/unit/test_product_behavior_eval_harness.py
.venv/bin/python -m py_compile <P7 boundary and real-gate files>
.venv/bin/ruff check <P7 boundary, focused tests and real-gate files>
git diff --check

odoo-bin --init=odoo_ai_assistant,odoo_ai_assistant_p7_fixture --test-enable --test-tags=/odoo_ai_assistant_p7_fixture --stop-after-init <disposable DB>
odoo-bin --init=odoo_ai_assistant --stop-after-init <fresh disposable DB>
odoo-bin --update=odoo_ai_assistant --test-enable --test-tags=/odoo_ai_assistant:TestAssistantTurnSettingsSnapshot --stop-after-init
node tests/e2e/phase23_hoot_gate.mjs  # three focused filters, explicit installed Chromium

PB_SUITE=full PB_SCENARIO=PB-ACT-010 PB_TRIALS=1 odoo-bin shell < tests/product_behavior/product_behavior_real_gate.py
PB_SUITE=full PB_SCENARIO=PB-ACT-001 PB_TRIALS=1 odoo-bin shell < tests/product_behavior/product_behavior_real_gate.py
PB_SUITE=smoke PB_TRIALS=1 odoo-bin shell < tests/product_behavior/product_behavior_real_gate.py
odoo-bin shell < tests/e2e/p7_real_provider_gate.py
odoo-bin shell < tests/e2e/p7_real_disclosure_gate.py
PB_SUITE=full PB_TRIALS=3 odoo-bin shell < tests/product_behavior/product_behavior_real_gate.py
```

The first disclosure attempt omitted the host's plan-unavailable state and the provider legitimately
returned `task_plan_update`; the corrected gate supplied the production host contract and passed.
An initial HOOT launch with WSL Node failed before tests because Playwright was unavailable there; a
second launch found the bundled package but not its expected browser revision. Neither is counted as
a test failure.

## Exact continuation

Using only the current configured Codex account after quota is available:

1. rerun Product Behavior FULL with `PB_SUITE=full PB_TRIALS=3` from the beginning (do not combine
   partial matrices into a false complete result);
2. repair/rerun any actual HARD failure;
3. run the final affected/full regression required by the periodic runbook;
4. publish final P7 acceptance evidence; only then set `P8 ELIGIBLE`.

No previous Codex account/session was used and no usage-reset credit was consumed.
