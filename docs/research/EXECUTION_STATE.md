# Stabilization execution state

State format: 3  
Updated: 2026-08-27  
Roadmaps: `FOUNDATION_STABILIZATION_PLAYBOOK.md` and `E2E_AGENT_LOOP_CONVERGENCE.md`

## Current cursor

```text
phase: 0
phase_name: reproducible baseline
phase_state: BLOCKED
active_slice: E2E-1-next-decision-contract
active_slice_state: READY
current_gate_type: HARD
next_phase: 1
```

General Phase 1 work remains locked. The only authorized production path is the bounded E2E
host-loop convergence needed to close the existing real ACTION hard gate.

## Published E2E checkpoints

### E2E-0 — decision-sequence fixtures and budgets

Status: COMPLETE for the deterministic E2E-0 contract gate.

Added a table-driven fixture for hello, READ, multi-read, patch, create, repairable validation,
access denial and unsupported action. Every case has explicit provider-decision/capability-call
bounds and the catalog defines transcript/result/correctable-failure ceilings for the later host
loop. The fixture records expected decision sequences rather than final prose.

Executed in the available environment on 2026-08-27:

```text
python tests/e2e/test_e2e_decision_sequences.py
4 tests, PASS
```

No product runtime behavior changed in E2E-0. Odoo-specific suites are not runnable in the current
execution environment and are not claimed as passed by this checkpoint.

## Look-ahead budget

```text
max_phase_distance_ahead: 1
max_unvalidated_implementation_slices: 2
max_stacked_unvalidated_contract_layers: 1
currently_consumed_implementation_slices: 0
currently_stacked_unvalidated_contract_layers: 0
```

The user has explicitly requested completing E2E-0 through E2E-4 in this implementation session.
Real Odoo/Codex gates must still be recorded as pending rather than claimed as passed.

## Existing real evidence that remains authoritative

- `P0-REAL-ACTION`: FAIL at `38c7c9a`; no preview/effect.
- `P0-REAL-ACTION-CORRECTED`: FAIL at `97617fe`; zero-step plan.
- `P0-REAL-ACTION-V2`: FAIL at `5995717`; effective planning catalog was exposed but Codex selected
  no tool and staged no proposal. First missing boundary: `plan_step_staged(odoo.record.patch)`.
- The v2 local targeted suites previously passed; the broad module run still carried separate
  `ODOO-CODEX-ACCOUNT-TEST-ISOLATION` debt.

Historical evidence remains under `docs/research/evidence/phase0/2026-08-27/` and is not rewritten.

## Validation debt

### VD-P0-ACTION-V2-REAL

```text
validation_id: P0-REAL-ACTION-V2
gate_type: HARD
origin_slice: pre-convergence ACTION v2
commit_materially_tested: 59957173510ec7f5da6d0ac39e9ea52244dbba86
reason: Codex emitted no tool call or plan proposal; E2E convergence is the approved correction
```

### VD-ACCOUNT-TEST-ISOLATION

```text
validation_id: ODOO-CODEX-ACCOUNT-TEST-ISOLATION
gate_type: SOFT during narrow E2E implementation, HARD before broad module regression is claimed green
origin_slice: P0 ACTION v2 local validation
reason: prior full-module run exposed one account connect/disconnect isolation failure
```

## Current blocker

```text
P0_ACTION_PROVIDER_CONTROL_LOOP_REQUIRED
```

## Exact next action

Implement E2E-1 only: strict provider-neutral `NextDecision` plus one-decision Codex structured
output. It must reject malformed unions, unknown capability identifiers and schema-invalid
arguments without executing a capability. No durable transcript/host loop belongs in E2E-1.

## Publication policy

- Work and publish coherent checkpoints directly to `main` without force-push.
- No GitHub Actions for this roadmap.
- Unrun tests remain debt.
- Never persist credentials, provider stdout/stderr, raw prompts, business values or private reasoning.
