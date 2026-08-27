# Stabilization execution state

State format: 3
Updated: 2026-08-27
Roadmaps: `FOUNDATION_STABILIZATION_PLAYBOOK.md` and `E2E_AGENT_LOOP_CONVERGENCE.md`

## Current cursor

```text
phase: 0
phase_name: reproducible baseline
phase_state: BLOCKED
active_slice: E2E-final-automated-battery-and-real-env-handoff
active_slice_state: READY
current_gate_type: HARD
next_phase: 1
```

General Phase 1 work remains locked. E2E-0 through E2E-4 have now been implemented locally; the
next work is the aggregate automated regression battery and a validation-only real-environment
handoff.

## Published convergence checkpoints

- E2E-0: decision-sequence fixtures and explicit provider/capability/byte budgets.
- E2E-1: strict provider-neutral `NextDecision`, host validation and tool-free one-decision Codex
  adapter.
- E2E-2: ADR-019 plus bounded private durable `working_items_payload`.
- E2E-3: active Odoo-owned iterative READ loop with REASONING-only execution, bounded correction,
  cancellation and restart/idempotency handling.
- E2E-4: one validated `PlanStepProposal` is canonical and stage-only. It feeds the existing
  `CapabilityPlanService.prepare` path directly. `plan_prepared` is persisted before effect;
  preview/approval/revalidation/write barrier/execute/verify/recovery remain authoritative.
  `verified_effect_receipt` is committed in the same Odoo transaction as effect/result/verification.
  The active path no longer depends on the old staged dynamic PLAN tool plus duplicated final plan
  serialization; that code remains only in the non-default rollback adapter.

## Tests actually executed in the available environment

Earlier slice evidence remains:

```text
E2E-0 dependency-light catalog: 4 tests PASS
E2E-1 dependency-light NextDecision: 4 tests PASS
E2E-1 standalone host-validator: 3 tests PASS
E2E-2 working-transcript contract: 4 tests PASS
E2E-3 mirrored host-loop contract: 7 tests PASS
Python compilation for each changed slice: PASS
```

For E2E-4 on 2026-08-27:

```text
python /tmp/e2e3_harness/test_canonical_plan_proposal.py
5 tests PASS

python -m py_compile \
  addons/odoo_ai_assistant/models/embedded_runtime_host_loop.py \
  addons/odoo_ai_assistant/tests/test_canonical_plan_host_loop.py
PASS
```

The Odoo TransactionCase canonical-plan tests were added but cannot execute in this environment
because an Odoo 18 checkout/runtime and PostgreSQL service are not available here. They remain
unrun, not passing.

## Required invariants preserved

Odoo remains operational authority. Business capabilities use the originating effective user with
`su=False`; ACLs, record rules, field access and company scope remain effective. `CapabilityDefinition`
and the effective catalog remain authoritative. The existing prepare, preview, approval,
revalidation, durable write barrier, PLAN execute, verification and recovery path is retained.
No new provider/API/RAG/router/tool selector, arbitrary SQL/Python/shell/sudo or generic ORM method
surface was introduced.

## Existing real evidence

The last pre-convergence real ACTION at `5995717` remains FAIL evidence. It is not converted into a
PASS by local implementation work. Its first missing boundary was the action proposal/staging
boundary.

## Validation debt

- `E2E-1-CODEX-DECISION-REAL`: real one-decision App Server round trip pending.
- `E2E-2-ODOO-PERSISTENCE`: module update and restart persistence pending.
- `E2E-3-REAL-HELLO-READ`: real hello, READ and multi-read pending.
- `E2E-4-REAL-ACTION`: disposable patch/create/action preview, one approval, exactly-one effect,
  verification and fixture cleanup pending.
- `ODOO-CODEX-ACCOUNT-TEST-ISOLATION`: broad-suite debt remains open.

## Exact next action

Add/run the complete automated convergence battery covering hello, READ, multi-read, patch, create,
repairable errors, access denied, unsupported action, restart/idempotency, approval, exactly-once
and verification. Then create `docs/research/E2E_REAL_ENV_HANDOFF.md` containing only real
validation work for the exact final implementation SHA and leave this state at
`REAL_ENV_VALIDATION_REQUIRED`. Do not claim any real Odoo/Codex/browser test has passed.
