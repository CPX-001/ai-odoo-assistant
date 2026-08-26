# Stabilization execution state

State format: 2  
Updated: 2026-08-27  
Latest repository checkpoint inspected: `c19f669f00d98a873c4dae04059269b8beed2d97`  
Latest product/tooling implementation checkpoint: `1b5c0ba857e61bbbbf7c8fc17f677bdabc87d892`  
Last real Odoo+Codex commit materially tested: `8641b013e62018d8d47cfb2a44106ff039b84aca`  
Roadmap: `FOUNDATION_STABILIZATION_PLAYBOOK.md`

## Current cursor

```text
phase: 0
phase_name: reproducible baseline
phase_state: REAL_ENV_VALIDATION_REQUIRED
active_slice: P0.1-partial-capture-and-retry-attribution
active_slice_state: LOCAL_VALIDATION_REQUIRED
current_gate_type: HARD
next_phase: 1
```

Phase 1 provider/runtime architecture work remains locked.

## Look-ahead budget

```text
max_phase_distance_ahead: 1
max_unvalidated_implementation_slices: 2
max_stacked_unvalidated_contract_layers: 1
currently_consumed_implementation_slices: 1
currently_stacked_unvalidated_contract_layers: 0
```

The consumed slice is a Phase 0 measurement-tooling correction, not a new production contract layer.

## Real evidence already processed

The first real Odoo 18 + Codex 0.149.1 run is recorded under
`docs/research/evidence/phase0/2026-08-27/` and remains authoritative for the current blocker.

Observed state:

- `P0-REAL-HELLO`: four completed captures from five submissions, with material provider instability;
- `P0-REAL-READ`: FAIL — no successful capability-backed read/tool evidence;
- `P0-REAL-ACTION`: FAIL — no preview/approval, provider child crashes coincided with Odoo service loss/restart;
- failure-pair matrix: only one current complete original/UI pair;
- `phase0_report.py`: `ready_for_phase1=false`.

## Active corrective slice — P0.1

Evidence record:
`docs/research/evidence/phase0/2026-08-27/P0.1-partial-capture-and-retry-attribution.md`

Implemented at `1b5c0ba857e61bbbbf7c8fc17f677bdabc87d892`:

- interrupted polling now returns a sanitized partial trace rather than discarding collected evidence;
- capture-side failures use `capture_error_code` and remain `expectation_met=false`;
- recovered transient diagnostic failures are no longer promoted to terminal `original_error_code` on successful turns;
- deterministic regression tests were added for both behaviors.

Validation status for this run:

```text
source/diff inspection: PASS
pytest: NOT RUN
py_compile: NOT RUN
real Odoo interrupted-capture validation: NOT RUN
```

Reason: this scheduled/remote run has GitHub repository access but no executable checkout/Odoo runtime. Unrun validation is not treated as PASS.

## Validation debt

### VD-P0.1-LOCAL

```text
validation_ids:
  - P0.1-UNIT
  - P0.1-PYCOMPILE
gate_type: HARD
origin_slice: P0.1-partial-capture-and-retry-attribution
commit_materially_tested: pending
blocked_scope:
  - marking P0.1 COMPLETE
  - relying on the new capture behavior for subsequent live evidence
reason: deterministic tests were added but could not be executed in the GitHub-only run
```

Required commands in an executable repository environment:

```bash
pytest -q tests/unit/test_phase0_live_capture.py
python -m py_compile tests/e2e/phase0_live_capture.py
```

### VD-P0.1-REAL

```text
validation_id: P0.1-REAL-PARTIAL-CAPTURE
gate_type: HARD
origin_slice: P0.1-partial-capture-and-retry-attribution
commit_materially_tested: pending
blocked_scope:
  - trusting interrupted live captures as preserved evidence
reason: exact implementation commit has not yet been exercised against a real interrupted Odoo polling path
```

Pass condition: the output trace is written, sanitized, retains already collected snapshots/timing, has `capture_error_code`, and remains `expectation_met=false`.

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
P0_1_DETERMINISTIC_AND_REAL_VALIDATION_PENDING
```

This blocker is narrower than the original live-run failure: P0.1 code exists, but must be tested before its measurement behavior is trusted.

## Exact next action selection

1. If executable local/Odoo evidence for commit `1b5c0ba857e61bbbbf7c8fc17f677bdabc87d892` is available, process it first.
2. Run `P0.1-UNIT` and `P0.1-PYCOMPILE` in an executable repository environment.
3. Run one bounded `P0.1-REAL-PARTIAL-CAPTURE` validation.
4. If P0.1 fails, create the smallest corrective child slice and keep Phase 0 open.
5. If P0.1 passes, mark it COMPLETE and make `P0.2-read-failure-diagnosis` the next normal Phase 0 slice.
6. Do not retry ACTION until READ passes and the provider/Odoo crash path is bounded.

## Planned corrective Phase 0 slices

- `P0.1-partial-capture-and-retry-attribution` — implemented, validation pending;
- `P0.2-read-failure-diagnosis` — reproduce why completed READ produced no tool-backed result and tighten acceptance evidence;
- `P0.3-provider-crash-reproduction` — isolate Codex 0.149.1 child signal-5 crashes and Odoo service loss before another write attempt;
- `P0.4-fault-injection-fixtures` — bounded EOF/timeout/invalid-output fixtures for the required failure-pair matrix;
- repeat READ, then ACTION, then aggregate Phase 0 report.

## Authorized look-ahead

`P1-PREP-CONFORMANCE` remains potentially useful and does not create a production contract layer, but it is **not the current priority** while a failed HARD Phase 0 gate has direct corrective work available.

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

Every new run must re-read current `main`, this file, the active evidence record, current code/tests and the continuous execution protocol before selecting work. Process new validation evidence before implementing another slice.
