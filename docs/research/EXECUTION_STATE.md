# Stabilization execution state

State format: 2  
Updated: 2026-08-27  
Latest repository checkpoint inspected: `8c21be0671bfb8f7df158cf32e6f624c043f7de6`  
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

The consumed look-ahead slice is `P1-PREP-CONFORMANCE`, adapter-neutral test preparation only. It is COMPLETE. No additional look-ahead slice is explicitly authorized for the current ACTION gate. The pending validation touches writes/approval/exactly-once behavior, so downstream provider/runtime implementation is not eligible under the protocol's look-ahead test.

## Processed real evidence

- `P0-REAL-HELLO`: baseline exists; original Codex 0.149.1 run showed provider instability.
- `P0-REAL-READ`: PASS at `a05e750`.
- `P0.3-REAL-READONLY-CRASH-PROBE`: PASS at `c114f15`.
- `P0.4-REAL-PROVIDER-EOF-PAIR`: PASS at `9008821`; `codex_process_eof -> service_unavailable`.
- `P0.4-REAL-PROVIDER-TIMEOUT-PAIR`: PASS at `9008821`; `codex_read_timeout -> service_unavailable`.
- `P0.4-REAL-INVALID-OUTPUT-PAIR`: PASS at `9008821`; `codex_answer_invalid -> service_unavailable`.
- `provider_auth_missing`: PASS pair at `9008821`; `codex_not_connected -> codex_not_connected`.
- failure-pair matrix: PASS with five distinct paths.
- aggregate Phase 0 report: timing decomposition PASS, simple latency attribution PASS, five failure pairs PASS, minimum live matrix FAIL only because `action=false`; `ready_for_phase1=false`.
- `P0-REAL-ACTION`: historical FAIL; no new ACTION evidence is present on current `main`.

## Completed corrective slices

- P0.1 partial capture/retry attribution — COMPLETE.
- P0.2 read failure diagnosis/acceptance — COMPLETE.
- P0.3 provider crash reproduction — COMPLETE.
- P0.4 bounded provider fault fixtures — COMPLETE.
- P1-PREP-CONFORMANCE — COMPLETE as test-only look-ahead; it does not authorize Phase 1 production work.

## Validation debt

### VD-P0-LIVE-BASELINE

```text
validation_id: P0-REAL-ACTION
gate_type: HARD
origin_slice: Phase 0 minimum live matrix
commit_materially_tested: pending current ACTION rerun
downstream_scope_blocked:
  - completing Phase 0
  - Phase 1 production provider/runtime refactor
  - provider lifecycle optimization
reason: the safe disposable ACTION baseline has not been rerun after P0.3/P0.4 bounded the prior provider/service instability
```

## Current blocker

```text
P0_REAL_ACTION_RERUN_REQUIRED
```

This repository-only run has GitHub access but no real Odoo 18 + authenticated Codex + browser execution path. No ACTION validation or deterministic product test was run here, and none is claimed as PASS.

## Action gate evidence handoff

Detailed procedure:
`docs/research/evidence/phase0/2026-08-27/P0-REAL-ACTION-handoff.md`

There are two distinct evidence requirements for this final Phase 0 gate:

1. **Authoritative real ACTION evidence** — one browser/Odoo/Codex turn must reach preview, explicit approval, exactly one effect and host verification under the normal product path.
2. **Machine-readable Phase 0 report evidence** — `phase0_report.py` only counts `action=true` when it receives an accepted `capture_kind=live_http` write scenario. The current capture runner supports only `entrypoint=enqueue`, so it can capture `write_preview` but cannot itself drive `write_execute_verify` (`entrypoint=plan_decision`).

The machine write-preview capture is measurement evidence only. It does not replace the real ACTION gate. If it is created as a separate turn, reject that preview after saving the capture so it cannot create a second business effect.

## Exact next action

1. Update/restart the disposable Odoo 18 environment from current `main` and verify Codex is authenticated.
2. Prepare one disposable partner, use a policy that requires confirmation, and record the original value of one harmless reversible field (for example `phone`).
3. Through the real Assistant browser UI, request exactly one update to that field.
4. Require an `awaiting_confirmation` preview that identifies the intended record and exact change; verify the record is still unchanged before approval.
5. Approve once through the supported UI.
6. Require exactly one execution and verification; confirm the Odoo record contains the intended value, no blind retry occurred, no ambiguous recovery state exists, and Odoo remained stable.
7. Record sanitized `P0-REAL-ACTION` evidence: commit tested, Odoo/Codex versions, preview/approval observed, execution/verification outcome, service stability, and artifact refs. Do not commit prompts, credentials, raw tool/provider payloads, or sensitive business data.
8. Restore the disposable field to its original value after authoritative evidence is captured.
9. Produce one sanitized `write_preview` capture with `tests/e2e/phase0_live_capture.py`; require exit `0`, `expectation_met=true` and final `awaiting_confirmation`. If this is a separate turn, reject it without approving it.
10. Rerun `tests/e2e/phase0_report.py` over the current sanitized live captures plus the new `write_preview` capture. Phase 1 may begin only if it exits `0` with `ready_for_phase1=true` **and** the authoritative browser `P0-REAL-ACTION` evidence above passed.
11. If Odoo restarts/becomes unhealthy, preview is missing/ambiguous, the effect occurs more than once, verification fails, or the write outcome is uncertain, stop immediately and record `P0-REAL-ACTION: FAIL`; do not begin Phase 1.

## Publication policy

- No GitHub Actions.
- Unrun tests remain debt.
- Publish coherent checkpoints to `origin/main` without force-push.
- Never publish credentials, raw provider output or unsanitized business evidence.
