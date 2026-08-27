# Stabilization execution state

State format: 3  
Updated: 2026-08-27  
Roadmaps: `FOUNDATION_STABILIZATION_PLAYBOOK.md` and `E2E_AGENT_LOOP_CONVERGENCE.md`

## Current cursor

```text
phase: 0
phase_name: reproducible baseline
phase_state: BLOCKED
active_slice: E2E-2-durable-working-transcript
active_slice_state: READY
current_gate_type: HARD
next_phase: 1
```

General Phase 1 work remains locked. The authorized production path is the bounded E2E host-loop
convergence required to close the existing real ACTION hard gate.

## Published E2E checkpoints

### E2E-0 — decision-sequence fixtures and budgets

Status: COMPLETE for its deterministic contract gate.

```text
python tests/e2e/test_e2e_decision_sequences.py
4 tests, PASS
```

### E2E-1 — strict NextDecision and one-decision Codex adapter

Status: implementation complete; real Codex protocol validation remains pending.

Implemented a strict provider-neutral union with exactly one branch per provider decision:
`final_answer`, `reasoning_capability_call` or `plan_step_proposal`. Host validation resolves the
selected identifier against the effective REASONING/PLAN catalog and validates arguments against
the current `CapabilityDefinition` schema without executing anything. The new Codex decision
adapter starts an ephemeral read-only App Server turn with `dynamicTools=[]` and a strict structured
output schema; it cannot execute a capability itself.

Executed in the available environment on 2026-08-27:

```text
python tests/e2e/test_next_decision_contract.py
4 tests, PASS

standalone host-validation harness equivalent to decision_validation.py
3 tests, PASS

python -m py_compile contracts.py decision_validation.py codex_decision.py
PASS
```

The Odoo TransactionCase added for effective-catalog/schema validation and a real Codex one-decision
round trip cannot run in the current execution environment and are not claimed as passed.

## Existing real evidence that remains authoritative

- `P0-REAL-ACTION`: FAIL at `38c7c9a`; no preview/effect.
- `P0-REAL-ACTION-CORRECTED`: FAIL at `97617fe`; zero-step plan.
- `P0-REAL-ACTION-V2`: FAIL at `5995717`; planning catalog exposed but no tool/proposal. First
  missing boundary: `plan_step_staged(odoo.record.patch)`.
- `ODOO-CODEX-ACCOUNT-TEST-ISOLATION` remains separate broad-suite debt.

## Validation debt

### VD-E2E-CODEX-DECISION-REAL

```text
validation_id: E2E-1-CODEX-DECISION-REAL
gate_type: HARD before declaring real-environment convergence complete
origin_slice: E2E-1
commit_materially_tested: pending
reason: one-decision structured output requires real Odoo/Codex protocol validation
```

### VD-P0-ACTION-V2-REAL

```text
validation_id: P0-REAL-ACTION-V2
gate_type: HARD
origin_slice: pre-convergence ACTION v2
commit_materially_tested: 59957173510ec7f5da6d0ac39e9ea52244dbba86
reason: old monolithic provider flow never crossed the plan-proposal boundary
```

## Current blocker

```text
P0_ACTION_PROVIDER_CONTROL_LOOP_REQUIRED
```

## Exact next action

Before changing operational orchestration, record the required ADR for the host-owned iterative
loop and implement E2E-2 only: a private typed working transcript persisted on `odoo.ai.turn`, with
bounded serialization, monotonic sequence, call-id recovery semantics and no automatic exposure in
browser/public events.

## Publication policy

- Publish coherent checkpoints directly to `main` without force-push.
- No GitHub Actions for this roadmap.
- Unrun Odoo/Codex tests remain explicit debt.
- Never persist credentials, provider stdout/stderr, raw prompts or private reasoning in public evidence.
