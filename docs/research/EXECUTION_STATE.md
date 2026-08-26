# Stabilization execution state

State format: 2  
Updated: 2026-08-27  
Latest repository checkpoint inspected: `baef228d47c25a7ecfdf582938bf5416fcae9121`  
Latest product/tooling implementation checkpoint: `fee7c4ee8b532e4529ad5dfd6249caab2c877a88`  
Latest P0.1 validation checkpoint materially tested: `121108e55ef0ff91adb0377920f73128875536ac`  
Last real Odoo+Codex commit materially tested: `121108e55ef0ff91adb0377920f73128875536ac`  
Roadmap: `FOUNDATION_STABILIZATION_PLAYBOOK.md`

## Current cursor

```text
phase: 0
phase_name: reproducible baseline
phase_state: REAL_ENV_VALIDATION_REQUIRED
active_slice: P0.2-read-failure-diagnosis
active_slice_state: REAL_ENV_VALIDATION_REQUIRED
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

The consumed slice is Phase 0 measurement/evidence tooling only; it does not create a production runtime contract layer.

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

Implemented at `1b5c0ba857e61bbbbf7c8fc17f677bdabc87d892` and materially validated at `121108e55ef0ff91adb0377920f73128875536ac`.

Validation status:

```text
pytest: PASS — 7 tests
py_compile: PASS
P0.1-REAL-PARTIAL-CAPTURE: PASS
recovered transient real observation: NOT OBSERVED (deterministic regression PASS)
```

`VD-P0.1-LOCAL` and `VD-P0.1-REAL` are closed.

## Active corrective slice — P0.2

Evidence record:
`docs/research/evidence/phase0/2026-08-27/P0.2-read-acceptance-evidence.md`

Implemented at `fee7c4ee8b532e4529ad5dfd6249caab2c877a88`:

- added a sanitized READ acceptance evaluator for `read_partner`, `query_sales`, and `aggregate_sales`;
- a READ now needs final `completed` state plus observed `tool.started` and `tool.completed` evidence to pass the machine gate;
- request/capture errors reject the READ even if tool events were observed;
- the evaluator does not consume answer text, prompts, raw tool/provider data, credentials, or private reasoning;
- product runtime, Odoo authority, capability execution, ACLs and `su=False` behavior are unchanged.

Deterministic validation actually executed against the exact published implementation contents:

```text
python -m pytest -q tests/unit/test_phase0_read_acceptance.py
3 passed in 0.05s

python -m py_compile tests/e2e/phase0_read_acceptance.py
PASS
```

This closes the acceptance false-positive part of P0.2, but not the real READ diagnosis/pass requirement.

## Validation debt

### VD-P0.2-REAL-READ

```text
validation_id: P0-REAL-READ
gate_type: HARD
origin_slice: P0.2-read-failure-diagnosis
commit_materially_tested: pending
downstream_scope_blocked:
  - marking P0.2 COMPLETE
  - retrying P0-REAL-ACTION
  - Phase 1 runtime/provider contract refactor
reason: exact current implementation has not yet produced a capability-backed known-partner READ in the real Odoo+Codex environment
```

### VD-P0-LIVE-BASELINE

```text
validation_ids:
  - P0-REAL-READ
  - P0-REAL-ACTION
  - P0-REAL-FAILURE-PAIR-* (>= 5 distinct paths)
gate_type: HARD
commit_materially_tested: mixed; last broad live baseline 8641b013e62018d8d47cfb2a44106ff039b84aca
downstream_scope_blocked:
  - Phase 1 runtime/provider contract refactor
  - provider lifecycle optimization
  - architecture decisions that depend on successful read/action/failure baseline evidence
reason: READ and ACTION failed and the failure-pair matrix is incomplete
```

## Current blocker

```text
P0_REAL_READ_REQUIRED_AND_PROVIDER_RUNTIME_UNSTABLE
```

P0.2 cannot complete until the real known-partner READ is rerun on current `main`. ACTION must remain frozen until READ passes and the provider/Odoo crash path is bounded.

## Exact next action selection

1. In the real Odoo 18 + Codex environment, update/restart from current `main`.
2. Run one bounded `read_partner` capture using the known disposable/demo partner and non-sensitive fields.
3. Run `tests/e2e/phase0_read_acceptance.py <capture.json> --out <acceptance.json>`.
4. Require exit `0`, `accepted=true`, observed `tool.started` + `tool.completed`, and a browser answer matching the actual partner data.
5. If READ fails, classify the sanitized evidence as provider/account/runtime vs capability selection/input/execution and create the smallest corrective child slice.
6. If READ passes, close `VD-P0.2-REAL-READ`, mark P0.2 COMPLETE, then begin `P0.3-provider-crash-reproduction` before any ACTION retry.
7. Do not begin Phase 1 production provider/runtime work.

## Planned corrective Phase 0 slices

- `P0.1-partial-capture-and-retry-attribution` — **COMPLETE**;
- `P0.2-read-failure-diagnosis` — **REAL_ENV_VALIDATION_REQUIRED**;
- `P0.3-provider-crash-reproduction` — next normal slice after P0.2 closes;
- `P0.4-fault-injection-fixtures` — bounded EOF/timeout/invalid-output fixtures;
- repeat READ/ACTION only under the stop rules, then aggregate Phase 0 report.

## Authorized look-ahead

`P1-PREP-CONFORMANCE` remains potentially eligible only if a later run is blocked solely by unavailable real-environment evidence and the protocol's eligibility test is satisfied. It is not authorized as a substitute for the current HARD P0.2 real READ gate.

No Phase 1 production provider/runtime refactor is authorized.

## Phase transition rule

Phase 0 remains incomplete until the mandatory real matrix, timing/tool decomposition and at least five distinct original/UI failure pairs pass and `phase0_report.py` reports `ready_for_phase1=true` on materially tested evidence.

## Automation / publication policy

- Do not use GitHub Actions; no runners/workers are available for this roadmap.
- Tests only count when actually executed.
- A remote/GitHub-only run records validation debt rather than assuming success.
- Roadmap checkpoints must be published to `origin/main` when possible so later runs can consume them.
- Never force-push or publish credentials/unsanitized real-environment evidence.

## Resume instructions

Every new run must re-read current `main`, this file, the P0.2 evidence record, current code/tests and the continuous execution protocol before selecting work. Process new real READ evidence first. Do not retry ACTION or begin Phase 1 while `VD-P0.2-REAL-READ` remains open.
