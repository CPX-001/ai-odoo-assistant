# Stabilization execution state

State format: 2  
Updated: 2026-08-27  
Latest repository checkpoint inspected: `819564b46eaa035ed4c685a170c227751e12b7a8`  
Latest product/tooling implementation checkpoint: `819564b46eaa035ed4c685a170c227751e12b7a8`  
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

Phase 1 provider/runtime architecture work remains locked.

## Look-ahead budget

```text
max_phase_distance_ahead: 1
max_unvalidated_implementation_slices: 2
max_stacked_unvalidated_contract_layers: 1
currently_consumed_implementation_slices: 1
currently_stacked_unvalidated_contract_layers: 0
```

The consumed slice is Phase 0 diagnostic tooling only; it changes no production runtime contract.

## Real evidence already processed

- `P0-REAL-HELLO`: baseline exists, with provider instability in the original Codex 0.149.1 run.
- `P0-REAL-READ`: PASS at `a05e750` with a capability-backed known-partner read and matching browser answer.
- `P0-REAL-ACTION`: FAIL in the original run; no preview/approval, with provider child signal-5 failures and one Odoo restart.
- failure-pair matrix: incomplete; only one complete current original/UI pair.
- Phase 0 aggregate gate remains `ready_for_phase1=false`.

## Completed corrective slices

### P0.1 — COMPLETE

Partial live captures are preserved and recovered transient diagnostics are not promoted to terminal
errors. Deterministic and real partial-capture validation passed.

### P0.2 — COMPLETE

READ acceptance now requires capability evidence. `P0-REAL-READ` passed at
`a05e75006f53b056f31ab96c3864092d89199480`.

## Active corrective slice — P0.3

Evidence record:
`docs/research/evidence/phase0/2026-08-27/P0.3-provider-crash-reproduction.md`

Implemented diagnostic tooling:

- bounded read-only `hello`/`read_partner` probe;
- before/after systemd identity/restart sampling;
- sanitized journal signal-5/code-mode-host counters;
- no product runtime or business-write behavior changed.

Static inspection of the current Codex boundary shows POSIX App Server processes are launched in a
new session and shutdown escalation targets the provider process group. This does not prove the
historical Odoo restart was unrelated; real evidence is still mandatory.

Deterministic validation actually executed against the exact probe/test contents:

```text
python -m py_compile tests/e2e/phase0_provider_crash_probe.py
PASS

python -m pytest -q tests/unit/test_phase0_provider_crash_probe.py
3 passed in 0.07s
```

The execution host printed unrelated spreadsheet-runtime warmup diagnostics to stderr, but both
validation commands exited 0.

## Validation debt

### VD-P0.3-REAL

```text
validation_id: P0.3-REAL-READONLY-CRASH-PROBE
gate_type: HARD
origin_slice: P0.3-provider-crash-reproduction
commit_materially_tested: pending
downstream_scope_blocked:
  - marking P0.3 COMPLETE
  - retrying P0-REAL-ACTION
  - Phase 1 runtime/provider contract refactor
reason: the new bounded read-only crash probe has not yet run inside real Odoo 18 + Codex
```

### VD-P0-LIVE-BASELINE

```text
validation_ids:
  - P0-REAL-ACTION
  - P0-REAL-FAILURE-PAIR-* (>= 5 distinct paths)
gate_type: HARD
downstream_scope_blocked:
  - Phase 1 runtime/provider contract refactor
  - provider lifecycle optimization
reason: ACTION is still frozen by P0.3 and the failure-pair matrix is incomplete
```

## Current blocker

```text
P0_3_REAL_READONLY_CRASH_PROBE_REQUIRED
```

## Exact next action

1. Update/restart the disposable Odoo 18 environment from current `main`.
2. Run `P0.3-REAL-READONLY-CRASH-PROBE` with three `hello` attempts.
3. Require stable Odoo MainPID/restart identity and `active/running` after every attempt.
4. Correlate only sanitized signal-5/code-mode-host journal counters.
5. If needed, repeat once with the already validated `read_partner` fixture; never use a write scenario.
6. If Odoo restarts/unhealthy, stop and create the smallest corrective child slice.
7. If the path is safely bounded, close P0.3 and move to P0.4 fault-injection fixtures.
8. Do not retry ACTION or begin Phase 1 before P0.3 closes.

## Planned corrective Phase 0 slices

- `P0.1-partial-capture-and-retry-attribution` — **COMPLETE**;
- `P0.2-read-failure-diagnosis` — **COMPLETE**;
- `P0.3-provider-crash-reproduction` — **REAL_ENV_VALIDATION_REQUIRED**;
- `P0.4-fault-injection-fixtures` — next normal slice after P0.3 closes;
- then repeat ACTION under stop rules and finish the failure-pair matrix.

## Automation / publication policy

- Do not use GitHub Actions.
- Unrun real tests remain debt.
- Publish coherent checkpoints to `origin/main` without force-push.
- Never publish credentials, raw provider output, raw journals, or unsanitized business evidence.
