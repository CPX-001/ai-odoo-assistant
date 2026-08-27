# Stabilization execution state

State format: 3
Updated: 2026-08-27
Roadmaps: `FOUNDATION_STABILIZATION_PLAYBOOK.md` and `E2E_AGENT_LOOP_CONVERGENCE.md`

## Current cursor

```text
phase: 0
phase_name: reproducible baseline
phase_state: BLOCKED
active_slice: E2E-real-environment-validation
active_slice_state: REAL_ENV_VALIDATION_REQUIRED
current_gate_type: HARD
next_phase: 1
```

The implementation/convergence work requested through E2E-4 and the final automated battery is complete. General Phase 1 work remains locked until the real environment validates the exact implementation/test SHA below.

## Exact implementation/test SHA

```text
ee723a7d715970681ef1addffebcceb54dbd2027
```

Commits after that SHA in this close-out are documentation-only. `docs/research/E2E_REAL_ENV_HANDOFF.md` is the authoritative validation procedure.

## Published convergence checkpoints

- E2E-0: decision-sequence fixtures and explicit provider/capability/byte budgets.
- E2E-1: strict provider-neutral `NextDecision`, tool-free one-decision Codex adapter and host-side validation/revalidation.
- E2E-2: ADR-019 plus bounded private durable `working_items_payload`.
- E2E-3: active Odoo-owned iterative READ loop with REASONING-only execution, bounded correction, cancellation and restart/idempotency handling.
- E2E-4: one validated `PlanStepProposal` is canonical and stage-only. It feeds `CapabilityPlanService.prepare`; preview/approval/revalidation/write barrier/execute/verify/recovery remain authoritative and a verified private receipt is persisted with the effect result.
- E2E-final: added the aggregate 12-case dependency-light battery and an executable Odoo `TransactionCase` battery covering hello, READ, multi-read, patch, create, repairable errors, access denied, unsupported action, restart/idempotency, approval, exactly-once and verification. The focused canonical PLAN tests are now registered in the addon test suite.

The final slice changed tests/test registration and documentation only relative to `ff7631c6cb09cfc07a52638cd6d62664666fa781`; no runtime architecture was changed.

## Tests actually executed in the available environment

Earlier deterministic evidence remains:

```text
E2E-0 dependency-light catalog: 4 tests PASS
E2E-1 dependency-light NextDecision: 4 tests PASS at its checkpoint
E2E-1 standalone host-validator: 3 tests PASS
E2E-2 working-transcript contract: 4 tests PASS
E2E-3 mirrored host-loop contract: 7 tests PASS
E2E-4 canonical-plan dependency-light contract: 5 tests PASS
Python compilation for the implementation slices: PASS
```

For the final aggregate battery on 2026-08-27, the committed dependency-light test was executed in the available connector-backed reconstructed checkout mirror using the committed fixture/transcript contract and current asserted source boundaries:

```text
python tests/e2e/test_e2e_convergence_battery.py
............
Ran 12 tests in 0.001s
OK
```

That 12-test PASS covers the requested final categories at the dependency-light contract layer.

The newly added Odoo `TransactionCase` battery and the registered canonical-plan tests **cannot execute in this environment** because there is no Odoo 18 checkout/runtime plus PostgreSQL service. They are UNRUN, not PASS. The handoff contains the exact module update and Odoo test commands required to close that gap.

## Required invariants preserved

Odoo remains operational authority. Business capabilities use the originating effective user with `su=False`; ACLs, record rules, field access and company scope remain effective. `CapabilityDefinition` and the effective catalog remain authoritative. The existing prepare, preview, approval, revalidation, durable write barrier, PLAN execute, verification and recovery path is unchanged by the final slice.

No provider/API/RAG/router/tool selector, arbitrary SQL/Python/shell/sudo or generic ORM method surface was added.

## Existing real evidence

The last pre-convergence real ACTION evidence at `5995717` remains FAIL evidence. It is not converted into a PASS by automated tests or by this handoff. Its first missing boundary was the action proposal/staging boundary that E2E-3/E2E-4 were designed to replace with the host-owned decision loop and canonical plan proposal.

## Remaining validation debt

All remaining items are real-environment validation, not implementation tasks:

- exact-SHA standalone rerun from a real checkout;
- Odoo addon install/update and `TransactionCase` battery;
- real Codex one-decision round trip;
- durable transcript persistence across real worker/process restart;
- real HELLO;
- real READ against a disposable known partner;
- real ACTION against a disposable partner through preview, one explicit approval, exactly one barrier/effect and verification;
- sanitized evidence and fixture/database cleanup;
- broad Odoo/Codex account test isolation remains follow-up debt after this hard gate.

## Exact next action

Follow `docs/research/E2E_REAL_ENV_HANDOFF.md` against implementation/test SHA `ee723a7d715970681ef1addffebcceb54dbd2027` on a disposable Odoo 18/WSL2 validation database.

Do not claim `REAL_ENV_VALIDATION_REQUIRED` has passed until the handoff's standalone, Odoo test, HELLO, READ and ACTION criteria all pass. On failure, record the first failing boundary and return to implementation only if the evidence proves a product/test defect.
