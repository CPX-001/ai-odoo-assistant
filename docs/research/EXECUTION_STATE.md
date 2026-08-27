# Stabilization execution state

State format: 2  
Updated: 2026-08-27  
Latest repository checkpoint inspected: `90088215f247716b57e5c19c2502cc2d33a78e51`
Latest product/tooling implementation checkpoint: `85086dad0f04c534d447b279e4e15c1afb879148`  
Latest P0.1 validation checkpoint materially tested: `121108e55ef0ff91adb0377920f73128875536ac`  
Latest P0.2 / real READ checkpoint materially tested: `a05e75006f53b056f31ab96c3864092d89199480`  
Latest P0.3 real crash-probe checkpoint materially tested: `c114f15a1fe82d102df3c129661fca87ceaeb235`  
Latest P0.4 real fault-pair checkpoint materially tested: `90088215f247716b57e5c19c2502cc2d33a78e51`
Roadmap: `FOUNDATION_STABILIZATION_PLAYBOOK.md`

## Current cursor

```text
phase: 0
phase_name: reproducible baseline
phase_state: REAL_ENV_VALIDATION_REQUIRED
active_slice: P0-REAL-ACTION-rerun
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

The consumed look-ahead slice remains `P1-PREP-CONFORMANCE`, adapter-neutral test preparation only. P0.4 is normal Phase 0 work and creates no production contract layer.

## Processed real evidence

- `P0-REAL-HELLO`: baseline exists; original Codex 0.149.1 run showed provider instability.
- `P0-REAL-READ`: PASS at `a05e750`.
- `P0.3-REAL-READONLY-CRASH-PROBE`: PASS at `c114f15`.
- `P0.4-REAL-PROVIDER-EOF-PAIR`: PASS at `9008821`; `codex_process_eof -> service_unavailable`.
- `P0.4-REAL-PROVIDER-TIMEOUT-PAIR`: PASS at `9008821`; `codex_read_timeout -> service_unavailable`.
- `P0.4-REAL-INVALID-OUTPUT-PAIR`: PASS at `9008821`; `codex_answer_invalid -> service_unavailable`.
- `provider_auth_missing`: PASS pair at `9008821`; `codex_not_connected -> codex_not_connected`.
- `P0-REAL-ACTION`: historical FAIL; not rerun in this slice.
- failure-pair matrix: PASS with five distinct paths.
- aggregate Phase 0 report remains not ready for Phase 1.

## Completed corrective slices

- P0.1 partial capture/retry attribution — COMPLETE.
- P0.2 read failure diagnosis/acceptance — COMPLETE.
- P0.3 provider crash reproduction — COMPLETE.
- P0.4 bounded provider fault fixtures — COMPLETE.

## Closed corrective slice — P0.4

Evidence:
`docs/research/evidence/phase0/2026-08-27/P0.4-fault-injection-fixtures.md`

Implemented test-only bounded App Server fixtures for:

- provider EOF -> expected `codex_process_eof`;
- provider timeout -> expected `codex_read_timeout`;
- invalid final output -> expected `codex_answer_invalid`.

The timeout fixture stalls only the reasoning client's initialize request, leaving the account gate healthy and using the host-owned 5-second startup timeout. No dynamic tools or business writes are emitted by any fixture.

Deterministic validation actually run against the exact published fixture contents:

```text
python -m py_compile \
  tests/fixtures/phase0_codex_fault_app_server.py \
  tests/unit/test_phase0_codex_fault_fixture.py
PASS

python -m pytest -q tests/unit/test_phase0_codex_fault_fixture.py
6 passed in 12.49s
```

Revalidated on the pulled checkpoint:

```text
python -m pytest -q tests/unit/test_phase0_codex_fault_fixture.py
6 passed in 0.06s

python -m pytest -q tests/unit/test_phase0_*.py tests/unit/test_codex_provider_conformance.py
33 passed in 0.12s
```

Real Odoo/browser validation:

```text
provider_disconnect:  failed / codex_process_eof / UI service_unavailable
provider_timeout:     failed / codex_read_timeout / UI service_unavailable
invalid_final_output: failed / codex_answer_invalid / UI service_unavailable
```

Every fixture override was restored, real provider status returned to `authenticated`, and Odoo
remained stable during each measured trial. Full details and sanitized artifacts are in the P0.4
evidence record.

The aggregate report was executed with eleven sanitized captures and returned exit `2` as
expected for the one remaining gate:

```text
timing_decomposition: true
simple_latency_attributed: true
five_failure_pairs: true
minimum_live_matrix: false (action=false)
ready_for_phase1: false
```

## Validation debt

### VD-P0-LIVE-BASELINE

```text
validation_ids:
  - P0-REAL-ACTION
gate_type: HARD
downstream_scope_blocked:
  - Phase 1 production provider/runtime refactor
  - provider lifecycle optimization
reason: the safe disposable ACTION baseline has not been rerun
```

## Current blocker

```text
P0_REAL_ACTION_RERUN_REQUIRED
```

## Exact next action

1. Prepare one disposable partner and record its reversible field value.
2. Run `P0-REAL-ACTION` through the real browser: require preview and explicit approval.
3. Verify the effect occurred exactly once, record the sanitized receipt/evidence, then restore the fixture.
4. Stop on any Odoo instability, missing preview, blind retry or ambiguous write outcome.
5. Rerun `phase0_report.py`; begin Phase 1 only if the aggregate report says `ready_for_phase1=true`.

## Publication policy

- No GitHub Actions.
- Unrun tests remain debt.
- Publish coherent checkpoints to `origin/main` without force-push.
- Never publish credentials, raw provider output or unsanitized business evidence.
