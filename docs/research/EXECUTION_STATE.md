# Stabilization execution state

State format: 2  
Updated: 2026-08-27  
Latest repository checkpoint inspected: `c7ea9dbaba2cc0305ff0f3af2a34c8a3e9f7a829`  
Latest product/tooling implementation checkpoint: pending P1-PREP-CONFORMANCE commit  
Latest P0.1 validation checkpoint materially tested: `121108e55ef0ff91adb0377920f73128875536ac`  
Latest P0.2 / real READ checkpoint materially tested: `a05e75006f53b056f31ab96c3864092d89199480`  
Roadmap: `FOUNDATION_STABILIZATION_PLAYBOOK.md`

## Current cursor

```text
phase: 0
phase_name: reproducible baseline
phase_state: REAL_ENV_VALIDATION_REQUIRED
active_slice: P0.3-provider-crash-reproduction
active_slice_state: REAL_ENV_VALIDATION_REQUIRED
current_gate_type: HARD
next_phase: 1
```

Phase 1 production provider/runtime architecture remains locked.

## Look-ahead budget

```text
max_phase_distance_ahead: 1
max_unvalidated_implementation_slices: 2
max_stacked_unvalidated_contract_layers: 1
currently_consumed_implementation_slices: 2
currently_stacked_unvalidated_contract_layers: 0
```

Consumed work:

1. P0.3 diagnostic probe tooling;
2. `P1-PREP-CONFORMANCE`, adapter-neutral test/fixture preparation only.

The look-ahead budget is now exhausted. Do not start another look-ahead implementation slice until
the P0.3 real gate is processed.

## Real evidence already processed

- `P0-REAL-HELLO`: baseline exists, with provider instability in the original Codex 0.149.1 run.
- `P0-REAL-READ`: PASS at `a05e750` with capability-backed known-partner data and matching browser answer.
- `P0-REAL-ACTION`: FAIL in the original run; ACTION remains frozen.
- No new P0.3 real probe evidence is present on current `main`.
- failure-pair matrix remains incomplete.
- Phase 0 aggregate gate remains `ready_for_phase1=false`.

## Completed corrective slices

- `P0.1-partial-capture-and-retry-attribution` — **COMPLETE**.
- `P0.2-read-failure-diagnosis` — **COMPLETE**.

## Active corrective slice — P0.3

Evidence:
`docs/research/evidence/phase0/2026-08-27/P0.3-provider-crash-reproduction.md`

State: `REAL_ENV_VALIDATION_REQUIRED`.

Deterministic P0.3 probe validation already recorded:

```text
python -m py_compile tests/e2e/phase0_provider_crash_probe.py
PASS

python -m pytest -q tests/unit/test_phase0_provider_crash_probe.py
3 passed in 0.07s
```

### VD-P0.3-REAL

```text
validation_id: P0.3-REAL-READONLY-CRASH-PROBE
gate_type: HARD
origin_slice: P0.3-provider-crash-reproduction
commit_materially_tested: pending
downstream_scope_blocked:
  - marking P0.3 COMPLETE
  - retrying P0-REAL-ACTION
  - Phase 1 production provider/runtime refactor
reason: the bounded read-only crash probe has not yet run inside real Odoo 18 + Codex
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
reason: ACTION remains frozen by P0.3 and the failure-pair matrix is incomplete
```

## Current blocker

```text
P0_3_REAL_READONLY_CRASH_PROBE_REQUIRED
```

No eligible look-ahead budget remains.

## Exact next action

1. Update/restart the disposable Odoo 18 environment from current `main`.
2. Run `P0.3-REAL-READONLY-CRASH-PROBE` with three `hello` attempts using `tests/e2e/phase0_provider_crash_probe.py`.
3. Require Odoo to remain `active/running` with stable MainPID, NRestarts and start identity.
4. Correlate only sanitized signal-5/code-mode-host counters.
5. If necessary, repeat once with the validated `read_partner` fixture; never use a write scenario.
6. If Odoo restarts or becomes unhealthy, stop and create the smallest corrective P0.3 child slice.
7. If safely bounded, close P0.3 and start normal `P0.4-fault-injection-fixtures`.
8. Do not retry ACTION or start Phase 1 production implementation before P0.3 closes.

## Automation / publication policy

- Do not use GitHub Actions.
- Unrun tests remain debt.
- Publish coherent checkpoints to `origin/main` without force-push.
- Never publish credentials, raw provider output, raw journals, or unsanitized business evidence.
