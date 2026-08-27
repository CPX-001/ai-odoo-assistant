# Stabilization execution state

State format: 2  
Updated: 2026-08-27  
Latest repository checkpoint inspected: `ce794792be40b6d5420752c2f2c7530e35135eca`  
Latest product/tooling implementation checkpoint: pending P0.4 checkpoint  
Latest P0.1 validation checkpoint materially tested: `121108e55ef0ff91adb0377920f73128875536ac`  
Latest P0.2 / real READ checkpoint materially tested: `a05e75006f53b056f31ab96c3864092d89199480`  
Latest P0.3 real crash-probe checkpoint materially tested: `c114f15a1fe82d102df3c129661fca87ceaeb235`  
Roadmap: `FOUNDATION_STABILIZATION_PLAYBOOK.md`

## Current cursor

```text
phase: 0
phase_name: reproducible baseline
phase_state: REAL_ENV_VALIDATION_REQUIRED
active_slice: P0.4-fault-injection-fixtures
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
currently_consumed_implementation_slices: 1
currently_stacked_unvalidated_contract_layers: 0
```

The consumed look-ahead slice remains `P1-PREP-CONFORMANCE`, adapter-neutral test preparation only. P0.4 is normal Phase 0 work and creates no production contract layer.

## Processed real evidence

- `P0-REAL-HELLO`: baseline exists; original Codex 0.149.1 run showed provider instability.
- `P0-REAL-READ`: PASS at `a05e750`.
- `P0.3-REAL-READONLY-CRASH-PROBE`: PASS at `c114f15`.
- `P0-REAL-ACTION`: historical FAIL; not rerun in this slice.
- failure-pair matrix: still incomplete.
- aggregate Phase 0 report remains not ready for Phase 1.

## Completed corrective slices

- P0.1 partial capture/retry attribution — COMPLETE.
- P0.2 read failure diagnosis/acceptance — COMPLETE.
- P0.3 provider crash reproduction — COMPLETE.

## Active corrective slice — P0.4

Evidence:
`docs/research/evidence/phase0/2026-08-27/P0.4-fault-injection-fixtures.md`

Implemented test-only bounded App Server fixtures for:

- provider EOF -> expected `codex_process_eof`;
- provider timeout -> expected `codex_read_timeout`;
- invalid final output -> expected `codex_answer_invalid`.

The timeout fixture stalls only the reasoning client's initialize request, leaving the account gate healthy and using the host-owned 5-second startup timeout. No dynamic tools or business writes are emitted by any fixture.

Deterministic validation actually run:

```text
python -m py_compile \
  tests/fixtures/phase0_codex_fault_app_server.py \
  tests/unit/test_phase0_codex_fault_fixture.py
PASS

python -m pytest -q tests/unit/test_phase0_codex_fault_fixture.py
6 passed in 12.49s
```

No Odoo integration or real browser test was run here.

## Validation debt

### VD-P0.4-REAL-FAULT-PAIRS

```text
validation_ids:
  - P0.4-REAL-PROVIDER-EOF-PAIR
  - P0.4-REAL-PROVIDER-TIMEOUT-PAIR
  - P0.4-REAL-INVALID-OUTPUT-PAIR
gate_type: HARD
origin_slice: P0.4-fault-injection-fixtures
commit_materially_tested: pending
downstream_scope_blocked:
  - marking P0.4 COMPLETE
  - counting these three failure paths toward the Phase 0 five-pair gate
reason: deterministic fake-provider behavior passed, but backend+browser pairs require real Odoo
```

### VD-P0-LIVE-BASELINE

```text
validation_ids:
  - P0-REAL-ACTION
  - P0-REAL-FAILURE-PAIR-* (>= 5 distinct paths)
gate_type: HARD
downstream_scope_blocked:
  - Phase 1 production provider/runtime refactor
  - provider lifecycle optimization
reason: ACTION has not been rerun and the real failure-pair matrix is incomplete
```

## Current blocker

```text
P0_4_REAL_FAULT_PAIRS_REQUIRED
```

## Exact next action

1. Update/restart the disposable Odoo 18 environment from current `main`.
2. Preserve the current administrative `odoo_ai_assistant.codex_executable` value.
3. Run `P0.4-REAL-PROVIDER-EOF-PAIR` using `tests/fixtures/codex_phase0_eof`.
4. Run `P0.4-REAL-PROVIDER-TIMEOUT-PAIR` using `tests/fixtures/codex_phase0_timeout`.
5. Run `P0.4-REAL-INVALID-OUTPUT-PAIR` using `tests/fixtures/codex_phase0_invalid_output`.
6. For every trial require final `failed`, the manifest original error code, and an actually observed browser/UI error code; restore the executable override after each.
7. If any fixture causes a write path, Odoo restart/unhealthy state or mismatched original code, stop and create the smallest corrective child slice.
8. After the three pairs pass, process the failure matrix and only then select the safe disposable ACTION rerun.
9. Do not begin Phase 1 production implementation until the aggregate Phase 0 gate passes.

## Publication policy

- No GitHub Actions.
- Unrun tests remain debt.
- Publish coherent checkpoints to `origin/main` without force-push.
- Never publish credentials, raw provider output or unsanitized business evidence.
