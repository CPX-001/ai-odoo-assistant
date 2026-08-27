# Stabilization execution state

State format: 3  
Updated: 2026-08-27  
Roadmaps: `FOUNDATION_STABILIZATION_PLAYBOOK.md` and `E2E_AGENT_LOOP_CONVERGENCE.md`

## Current cursor

```text
phase: 0
phase_name: reproducible baseline
phase_state: BLOCKED
active_slice: E2E-4-canonical-plan-proposal
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
  `odoo.ai.turn.working_items_payload` field plus lease-bound persistence helper. Dependency-light
  transcript contract `4 tests, PASS`; module update/restart persistence remains real-env debt.
- E2E-3: `AgentTurnService` now owns a bounded iterative READ loop when composed with a
  `NextDecisionEngine`. The active embedded runtime uses `CodexDecisionEngine`; every provider
  decision is host-validated against the effective catalog, REASONING calls execute only with
  `ExecutionAuthority.REASONING`, read calls use the current Odoo cursor savepoint, private
  decisions/calls/results/errors are persisted at host boundaries, cancellation and global/per-
  capability budgets are enforced, and an interrupted persisted call id is closed as an explicit
  error instead of executing that same call id again. A terminal ACL/authority error may be
  followed only by a final explanation. PLAN proposals are deliberately not enabled in this
  checkpoint and remain E2E-4.

Executed for E2E-3 in the available environment on 2026-08-27:

```text
python /tmp/e2e3_harness/test_host_loop_contract.py
7 tests, PASS

python -m py_compile \
  runtime/agent/service.py \
  runtime/agent/decision_validation.py \
  runtime/agent/working_transcript.py \
  models/embedded_runtime_host_loop.py \
  tests/test_host_loop_agent_runtime.py
PASS
```

The Odoo `TransactionCase` host-loop test was added but cannot execute in this environment because
there is no Odoo checkout/runtime or PostgreSQL service here.

## Required invariants preserved

`CapabilityDefinition`, effective-catalog filtering, effective user `su=False`, ACL/record rules,
company scope, prepare/preview/approval/write barrier/execute/verify and post-barrier recovery are
unchanged. No provider/API/RAG/router/arbitrary SQL/Python/shell/sudo/generic ORM method surface was
added. The legacy monolithic Codex reasoning implementation remains only as the ADR-019 rollback
seam and is not the active embedded composition.

## Existing real evidence

The latest pre-convergence ACTION evidence remains FAIL at `5995717`; first missing boundary was
`plan_step_staged(odoo.record.patch)`. It is not overwritten by local implementation evidence.

## Validation debt

- `E2E-1-CODEX-DECISION-REAL`: real one-decision App Server round trip pending.
- `E2E-2-ODOO-PERSISTENCE`: module update/restart persistence test pending.
- `E2E-3-REAL-HELLO-READ`: real hello, READ and multi-read host-loop validation pending.
- `P0-REAL-ACTION-V2`: superseded implementation path remains failed evidence, not a PASS.
- `ODOO-CODEX-ACCOUNT-TEST-ISOLATION`: broad-suite debt remains open.

## Exact next action

Implement E2E-4: allow one validated `PlanStepProposal` to become the canonical stage-only
`PlannedCapability`, feed it directly into the unchanged `CapabilityPlanService.prepare` lifecycle,
persist the `plan_prepared` boundary, keep approval/revalidation/write-barrier/execute/verify/recovery
unchanged, and record a verified-effect receipt only in the same Odoo transaction that commits the
effect/result. Remove the old staged-tool/final-plan obligation from the active product path; keep it
only in the non-default rollback adapter until real validation closes the handoff.
