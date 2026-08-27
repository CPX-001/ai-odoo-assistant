# Stabilization execution state

State format: 3  
Updated: 2026-08-27  
Roadmaps: `FOUNDATION_STABILIZATION_PLAYBOOK.md` and `E2E_AGENT_LOOP_CONVERGENCE.md`

## Current cursor

```text
phase: 0
phase_name: reproducible baseline
phase_state: BLOCKED
active_slice: E2E-3-read-host-loop
active_slice_state: READY
current_gate_type: HARD
next_phase: 1
```

General Phase 1 work remains locked; only the E2E convergence required by the ACTION hard gate is
being implemented.

## Published E2E checkpoints

- E2E-0: decision-sequence fixtures/budgets complete; `4 tests, PASS` in available environment.
- E2E-1: strict `NextDecision`, host validation and tool-free one-decision Codex adapter implemented;
  dependency-light `4 tests, PASS`, standalone host-validator `3 tests, PASS`, compile PASS. Real
  Codex protocol validation remains pending.
- E2E-2: ADR-019 accepted. Added the bounded private typed working transcript and a durable
  `odoo.ai.turn.working_items_payload` field plus lease-bound persistence helper. The transcript is
  distinct from browser/public events and has monotonic sequence, call-id and byte-limit checks.

Executed for E2E-2 in the available environment on 2026-08-27:

```text
python tests/e2e/test_working_transcript_contract.py
4 tests, PASS

python -m py_compile working_transcript.py
PASS
```

Odoo module-install/update tests for the new stored field cannot run here and remain pending.

## Required invariants preserved

`CapabilityDefinition`, effective-catalog filtering, effective user `su=False`, ACL/record rules,
company scope, prepare/preview/approval/write barrier/execute/verify and post-barrier recovery are
unchanged. No provider/API/RAG/router/arbitrary SQL/Python/shell/sudo/generic ORM method surface was
added.

## Existing real evidence

The latest pre-convergence ACTION evidence remains FAIL at `5995717`; first missing boundary was
`plan_step_staged(odoo.record.patch)`. It is not overwritten by local implementation evidence.

## Validation debt

- `E2E-1-CODEX-DECISION-REAL`: real one-decision App Server round trip pending.
- `E2E-2-ODOO-PERSISTENCE`: module update/restart persistence test pending.
- `P0-REAL-ACTION-V2`: superseded implementation path remains failed evidence, not a PASS.
- `ODOO-CODEX-ACCOUNT-TEST-ISOLATION`: broad-suite debt remains open.

## Exact next action

Implement E2E-3: make `AgentTurnService` own the bounded iterative READ loop using
`CodexDecisionEngine`, persist every private boundary, execute only effective REASONING
capabilities under `ExecutionAuthority.REASONING`, return bounded capability errors for repair,
respect cancellation/budgets, and recover pending/completed call ids without duplicate execution.
Do not change the existing PLAN execution lifecycle in this slice.
