# Stabilization execution state

State format: 2  
Updated: 2026-08-27  
Latest repository checkpoint inspected: `121108e55ef0ff91adb0377920f73128875536ac`<br>
Latest product/tooling implementation checkpoint: `1b5c0ba857e61bbbbf7c8fc17f677bdabc87d892`  
Latest P0.1 validation checkpoint materially tested: `121108e55ef0ff91adb0377920f73128875536ac`<br>
Last real Odoo+Codex commit materially tested: `121108e55ef0ff91adb0377920f73128875536ac`<br>
Roadmap: `FOUNDATION_STABILIZATION_PLAYBOOK.md`

## Current cursor

```text
phase: 0
phase_name: reproducible baseline
phase_state: REAL_ENV_VALIDATION_REQUIRED
active_slice: P0.2-read-failure-diagnosis
active_slice_state: READY
current_gate_type: HARD
next_phase: 1
```

Phase 1 provider/runtime architecture work remains locked.

## Look-ahead budget

```text
max_phase_distance_ahead: 1
max_unvalidated_implementation_slices: 2
max_stacked_unvalidated_contract_layers: 1
currently_consumed_implementation_slices: 0
currently_stacked_unvalidated_contract_layers: 0
```

No unvalidated look-ahead implementation slice is currently carried.

## Real evidence already processed

The first real Odoo 18 + Codex 0.149.1 run is recorded under
`docs/research/evidence/phase0/2026-08-27/` and remains authoritative for the current blocker.

Observed state:

- `P0-REAL-HELLO`: four completed captures from five submissions, with material provider instability;
- `P0-REAL-READ`: FAIL — no successful capability-backed read/tool evidence;
- `P0-REAL-ACTION`: FAIL — no preview/approval, provider child crashes coincided with Odoo service loss/restart;
- failure-pair matrix: only one current complete original/UI pair;
- `phase0_report.py`: `ready_for_phase1=false`.

## Completed corrective slice — P0.1

Evidence record:
`docs/research/evidence/phase0/2026-08-27/P0.1-partial-capture-and-retry-attribution.md`

Implemented at `1b5c0ba857e61bbbbf7c8fc17f677bdabc87d892`:

- interrupted polling now returns a sanitized partial trace rather than discarding collected evidence;
- capture-side failures use `capture_error_code` and remain `expectation_met=false`;
- recovered transient diagnostic failures are no longer promoted to terminal `original_error_code` on successful turns;
- deterministic regression tests were added for both behaviors.

Validation status:

```text
source/diff inspection: PASS at 121108e
pytest: PASS — 7 tests
py_compile: PASS
P0.1-REAL-PARTIAL-CAPTURE: PASS
recovered transient real observation: NOT OBSERVED (deterministic regression PASS)
```

The real partial-capture gate used a loopback-only fault proxy: authentication and enqueue reached
real Odoo, then the first status poll returned a controlled HTTP 503. The runner wrote a sanitized
partial trace with the queued snapshot, available timings, `capture_error_code`,
`expectation_met=false` and no terminal `original_error_code`. Odoo was not stopped and remained
healthy after the test.

## Validation debt

`VD-P0.1-LOCAL` and `VD-P0.1-REAL` are closed at materially tested commit `121108e`.

### VD-P0-LIVE-BASELINE

```text
validation_ids:
  - P0-REAL-READ
  - P0-REAL-ACTION
  - P0-REAL-FAILURE-PAIR-* (>= 5 distinct paths)
gate_type: HARD
commit_materially_tested: 8641b013e62018d8d47cfb2a44106ff039b84aca
downstream_scope_blocked:
  - Phase 1 runtime/provider contract refactor
  - provider lifecycle optimization
  - architecture decisions that depend on successful read/action/failure baseline evidence
reason: READ and ACTION failed and the failure-pair matrix is incomplete
```

## Current blocker

```text
P0_READ_FUNCTIONAL_FAILURE_AND_PROVIDER_RUNTIME_UNAVAILABLE
```

P0.1 is complete. Phase 0 remains blocked from Phase 1 by the failed functional READ, incomplete
failure-pair matrix and unbounded provider/Odoo crash path. A non-injected `hello` during P0.1
validation also ended after three `runtime_unavailable` attempts; this is diagnostic context for
the existing Phase 0 work, not a P0.1 failure.

## Exact next action selection

1. Start `P0.2-read-failure-diagnosis` from current `main`.
2. Reproduce the bounded READ failure and distinguish provider/account/runtime availability from
   capability selection/input/execution failure.
3. Tighten READ acceptance evidence so a completed apology cannot count as a functional PASS.
4. Run the affected deterministic regression and the bounded real READ validation.
5. Do not retry ACTION until READ passes and the provider/Odoo crash path is bounded.

## Planned corrective Phase 0 slices

- `P0.1-partial-capture-and-retry-attribution` — **COMPLETE**;
- `P0.2-read-failure-diagnosis` — **READY**; reproduce why completed READ produced no tool-backed result and tighten acceptance evidence;
- `P0.3-provider-crash-reproduction` — isolate Codex 0.149.1 child signal-5 crashes and Odoo service loss before another write attempt;
- `P0.4-fault-injection-fixtures` — bounded EOF/timeout/invalid-output fixtures for the required failure-pair matrix;
- repeat READ, then ACTION, then aggregate Phase 0 report.

## Authorized look-ahead

`P1-PREP-CONFORMANCE` remains potentially useful and does not create a production contract layer,
but it is **not the current priority** while `P0.2` is READY and a failed HARD Phase 0 gate has
direct corrective work available.

No Phase 1 production provider/runtime refactor is authorized.

## Phase transition rule

Phase 0 remains incomplete until the mandatory real matrix, timing/tool decomposition and at least five distinct original/UI failure pairs pass and `phase0_report.py` reports `ready_for_phase1=true` on materially tested evidence.

## Automation / publication policy

- Do not use GitHub Actions; no runners/workers are available for this roadmap.
- Tests only count when actually executed.
- A remote/GitHub-only run records validation debt rather than assuming success.
- Roadmap checkpoints must be published to `origin/main` when possible so later scheduled runs can consume them.
- Never force-push or publish credentials/unsanitized real-environment evidence.

## Resume instructions

Every new run must re-read current `main`, this file, the P0.1 evidence record, current code/tests
and the continuous execution protocol before selecting work. The next run may begin P0.2, but must
not repeat ACTION or begin Phase 1.
