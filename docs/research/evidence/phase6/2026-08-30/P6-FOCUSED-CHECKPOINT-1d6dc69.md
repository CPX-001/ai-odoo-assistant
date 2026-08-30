# P6 planning / EffectPlan focused deterministic checkpoint

Date: 2026-08-30  
Tested code checkpoint: `1d6dc695f7fbb26a8d2bef578902d8ce2ebf56b9`  
Pulled base: `c2ecf96c`  
Result: **PASS — focused deterministic checkpoint**

## Scope

This run validated only the new or directly affected P6.1/P6.3/P6.5 contracts. It did **not** run a full addon, HOOT/browser or repository regression.

The focused risk boundaries were:

- provider-neutral TaskPlan parsing, monotonic revisions and separation from EffectPlan authority;
- bounded multi-step accumulation, ordering, one write barrier and per-step verification;
- remaining effect-step and provider-decision budgets;
- Codex four-way neutral decision translation;
- post-effect isolation, action revalidation and existing explicit compensation;
- closed browser validation and rendering integration for projected TaskPlan data.

## Results

```text
Dependency-light Python command                              PASS (264 tests)
  tests/unit
  test_phase6_planning_contract.py
  test_next_decision_contract.py
  test_canonical_plan_proposal.py

JavaScript dependency-light contracts                       PASS
  failure contract                                           14 assertions
  public activity contract                                   12 assertions

Changed/new P6 Odoo methods                                  PASS (8 tests)
  canonical TaskPlan / two-step EffectPlan                    5 tests
  Codex neutral wire contract                                 3 tests

Direct Odoo effect boundaries                               PASS (23 tests)
  post-effect reasoning
  action policy revalidation
  capability action/batch execution
  patch/archive/unarchive compensation                        3 focused methods

Focused HOOT TaskPlan browser gate                          PASS (1 test, 4 assertions)
  accepts a valid bounded TaskPlan
  rejects capability/execution authority fields
  rejects forward/unknown dependencies

TaskPlan XML parse                                           PASS
Changed JavaScript module syntax                             PASS
git diff --check                                             PASS
```

The first dependency-light command included the existing unit directory before the test-scope rule was clarified during this run. It is recorded honestly, but it is not precedent for rerunning broad suites. The authoritative repository rule is now incremental validation by default.

## Repair made

The server already reparsed and bounded TaskPlan before projection, but `normalizeChatResponse()` did not enforce the same closed contract at the browser boundary. The repair now validates exact TaskPlan/step keys, bounds, states, unique IDs and backward-only dependencies. It rejects executable authority such as `capability` in a visible TaskPlan step.

## Non-gating observations

Fresh addon installation emitted existing RST/docstring warnings and missing-access-rule warnings for the abstract turn-control/intervention helper models. The selected tests still completed with zero failures/errors. These warnings predate this focused repair and were not expanded into unrelated work.

## Remaining gates

No P6 real gate is marked PASS by this evidence. Still required:

```text
P6-REAL-MULTISTEP
P6-REAL-LOOP-BOUNDS
```

Full regression suites were not run and are not required by this checkpoint. They require an explicit user request or a future authoritative gate that names them.
