# Stabilization execution state

State format: 2  
Updated: 2026-08-27  
Latest repository checkpoint inspected: `c114f15a1fe82d102df3c129661fca87ceaeb235`
Latest product/tooling implementation checkpoint: `aa1e24d904ca34d0f9b7e842f5b0504dc9dc36ba`  
Latest P0.1 validation checkpoint materially tested: `121108e55ef0ff91adb0377920f73128875536ac`  
Latest P0.2 / real READ checkpoint materially tested: `a05e75006f53b056f31ab96c3864092d89199480`  
Latest P0.3 real crash-probe checkpoint materially tested: `c114f15a1fe82d102df3c129661fca87ceaeb235`
Roadmap: `FOUNDATION_STABILIZATION_PLAYBOOK.md`

## Current cursor

```text
phase: 0
phase_name: reproducible baseline
phase_state: IN_PROGRESS
active_slice: P0.4-fault-injection-fixtures
active_slice_state: READY
current_gate_type: HARD
next_phase: 1
```

Phase 1 production provider/runtime architecture remains locked.

## Look-ahead budget

```text
max_phase_distance_ahead: 1
max_unvalidated_implementation_slices: 2
max_stacked_unvalidated_contract_layers: 1
currently_consumed_implementation_slices: 1
currently_stacked_unvalidated_contract_layers: 0
```

Consumed work:

1. `P1-PREP-CONFORMANCE`, adapter-neutral test/fixture preparation only.

P0.4 is normal Phase 0 work and does not consume look-ahead budget. Phase 1 production work remains
locked by the aggregate Phase 0 gate.

## Real evidence already processed

- `P0-REAL-HELLO`: baseline exists, with provider instability in the original Codex 0.149.1 run.
- `P0-REAL-READ`: PASS at `a05e750` with capability-backed known-partner data and matching browser answer.
- `P0.3-REAL-READONLY-CRASH-PROBE`: PASS at `c114f15`; three greetings and one
  capability-backed read completed without Odoo restart, unhealthy state or signal-5 observation.
- `P0-REAL-ACTION`: FAIL in the original run; ACTION remains frozen.
- failure-pair matrix remains incomplete.
- Phase 0 aggregate gate remains `ready_for_phase1=false`.

## Completed corrective slices

- `P0.1-partial-capture-and-retry-attribution` — **COMPLETE**.
- `P0.2-read-failure-diagnosis` — **COMPLETE**.
- `P0.3-provider-crash-reproduction` — **COMPLETE**.

## Closed corrective slice — P0.3

Evidence:
`docs/research/evidence/phase0/2026-08-27/P0.3-provider-crash-reproduction.md`

State: `COMPLETE`.

Deterministic P0.3 probe validation already recorded:

```text
python -m py_compile tests/e2e/phase0_provider_crash_probe.py
PASS

python -m pytest -q tests/unit/test_phase0_provider_crash_probe.py
3 passed in 0.07s
```

Real validation executed on Odoo 18 Community with addon `18.0.10.4.6` and Codex CLI `0.144.2`:

```text
3 hello attempts: completed
1 read_partner attempt: completed; tool.started=3; reasoning.completed=1
Odoo restart/unhealthy observations: 0
signal-5 / code-mode-host failure lines: 0 / 0
journal available: 4 of 4 attempts
```

Sanitized artifacts and the detailed result are stored alongside the P0.3 evidence record. The
historical 0.149.1 event remains historical evidence; this PASS bounds the current environment and
does not claim a universal provider fix.

Deterministic revalidation on the pulled checkpoint:

```text
python -m py_compile tests/e2e/phase0_provider_crash_probe.py tests/contracts/codex_provider_conformance.py
PASS

python -m pytest -q tests/unit/test_phase0_provider_crash_probe.py tests/unit/test_codex_provider_conformance.py
7 passed in 0.04s

python -m pytest -q tests/unit/test_phase0_*.py tests/unit/test_codex_provider_conformance.py
27 passed in 0.10s
```

## Completed authorized look-ahead — P1-PREP-CONFORMANCE

Evidence:
`docs/research/evidence/phase0/2026-08-27/P1-PREP-CONFORMANCE.md`

Added only adapter-neutral test preparation:

- fourteen-case conformance manifest matching Phase 1.2;
- pure-Python adapter protocol/harness;
- evaluator requiring expected outcome plus safety assertions;
- no production runtime changes.

Deterministic validation actually executed:

```text
python -m py_compile tests/contracts/codex_provider_conformance.py
PASS

python -m pytest -q tests/unit/test_codex_provider_conformance.py
4 passed in 0.07s
```

This does not claim either the current custom Codex adapter or an SDK adapter conforms.

## Remaining Phase 0 debt

### VD-P0-LIVE-BASELINE

```text
validation_ids:
  - P0-REAL-ACTION
  - P0-REAL-FAILURE-PAIR-* (>= 5 distinct paths)
gate_type: HARD
downstream_scope_blocked:
  - Phase 1 runtime/provider contract refactor
  - provider lifecycle optimization
reason: ACTION has not yet been rerun after P0.3 closed, and the failure-pair matrix is incomplete
```

## Current blocker

```text
PHASE0_ACTION_AND_FAILURE_PAIR_EVIDENCE_REQUIRED
```

This blocks Phase 1 production runtime/provider changes but does not block normal P0.4 work.

## Exact next action

1. Start normal `P0.4-fault-injection-fixtures`.
2. Add bounded EOF/disconnect, timeout and invalid-output fixtures without weakening host authority.
3. Run deterministic fixture tests, then collect the corresponding real original/UI failure pairs.
4. Retry the safe disposable ACTION baseline only after the relevant Phase 0 stop rules remain satisfied.
5. Do not start Phase 1 production implementation until the aggregate Phase 0 hard gate passes.

## Automation / publication policy

- Do not use GitHub Actions.
- Unrun tests remain debt.
- Publish coherent checkpoints to `origin/main` without force-push.
- Never publish credentials, raw provider output, raw journals, or unsanitized business evidence.
