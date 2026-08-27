# Stabilization execution state

State format: 3
Updated: 2026-08-27
Roadmaps: `FOUNDATION_STABILIZATION_PLAYBOOK.md` and `E2E_AGENT_LOOP_CONVERGENCE.md`

## Current cursor

```text
phase: 0
phase_name: reproducible baseline
phase_state: BLOCKED
active_slice: E2E-turn-event-serialization-correction
active_slice_state: READY
current_gate_type: HARD
next_phase: 1
```

The implementation/convergence work requested through E2E-4 and the final automated battery is
complete. Exact-SHA validation proved the Codex adapter repair and exposed a separate turn/event
transaction defect. General Phase 1 work remains locked until that defect is corrected and the full
real gate passes.

## Exact implementation/test SHA

```text
e9420ae80cf1d6a030312e5e4e76a911c60c7b18
```

Commits after that SHA in this close-out are documentation-only. `docs/research/E2E_REAL_ENV_HANDOFF.md` is the authoritative validation procedure.

## Published convergence checkpoints

- E2E-0: decision-sequence fixtures and explicit provider/capability/byte budgets.
- E2E-1: strict provider-neutral `NextDecision`, tool-free one-decision Codex adapter and host-side validation/revalidation.
- E2E-2: ADR-019 plus bounded private durable `working_items_payload`.
- E2E-3: active Odoo-owned iterative READ loop with REASONING-only execution, bounded correction, cancellation and restart/idempotency handling.
- E2E-4: one validated `PlanStepProposal` is canonical and stage-only. It feeds `CapabilityPlanService.prepare`; preview/approval/revalidation/write barrier/execute/verify/recovery remain authoritative and a verified private receipt is persisted with the effect result.
- E2E-final: added the aggregate 12-case dependency-light battery and an executable Odoo `TransactionCase` battery covering hello, READ, multi-read, patch, create, repairable errors, access denied, unsupported action, restart/idempotency, approval, exactly-once and verification. The focused canonical PLAN tests are now registered in the addon test suite.
- E2E-real-adapter repair: the one-decision Codex adapter now translates the strict provider-neutral union into an App Server-compatible Structured Outputs envelope, decodes bounded `arguments_json` back into the unchanged contract, and preserves `codex_output_schema_invalid` for the observed rejection.

The E2E-final slice changed tests/test registration and documentation only relative to `ff7631c6cb09cfc07a52638cd6d62664666fa781`; no runtime architecture was changed. The later adapter repair changes only the provider wire representation and diagnostic normalization, not host authority or lifecycle architecture.

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

The first real convergence validation at `ee723a7d715970681ef1addffebcceb54dbd2027`
reported the standalone battery PASS, the Odoo convergence `TransactionCase` battery 12/12 PASS
and the focused canonical PLAN battery 2/2 PASS. The first real HELLO then failed after three
provider attempts while Odoo remained stable: `write_barrier=false`, the working transcript held
only `user_input`, and no decision/capability/proposal boundary was reached. Local reproduction
against Codex App Server 0.149.1 identified an HTTP 400 `invalid_json_schema`: root `oneOf` was not
permitted and the adapter had collapsed the error to `codex_turn_failed`.

At `e9420ae80cf1d6a030312e5e4e76a911c60c7b18`, the following repair checks were actually executed:

```text
standalone convergence battery: 12/12 PASS
decision sequences: 4/4 PASS
NextDecision contract: 4/4 PASS
working transcript contract: 4/4 PASS
canonical plan contract: 5/5 PASS
one-decision adapter regressions: 3/3 PASS
Python compilation: PASS
real Codex App Server one-decision greeting: PASS (final_answer)
```

The last check used the real installed App Server and an authenticated local provider home.

The exact-SHA product-path rerun then executed on Odoo 18 with Codex 0.149.1 in a new disposable
database:

```text
standalone convergence: 12/12 PASS
decision sequences: 4/4 PASS
NextDecision contract: 4/4 PASS
working transcript contract: 4/4 PASS
canonical plan contract: 5/5 PASS
Python compilation: PASS
fresh install and explicit addon update: PASS
Odoo convergence: 12/12 PASS
Odoo canonical PLAN: 2/2 PASS
Odoo one-decision adapter: 3/3 PASS
real HELLO: completed after 1 runtime_unavailable requeue (hard-gate FAIL)
real READ: failed/runtime_unavailable after 3 attempts (FAIL)
real ACTION: NOT RUN because READ failed
fixture/database cleanup: PASS
```

The adapter returned valid decisions. The new first failed product boundary was an independent
event append updating `odoo_ai_turn.last_event_sequence` while the primary turn transaction still
held the same record. Its next flush/commit raised PostgreSQL `SerializationFailure`. See
`docs/research/evidence/phase0/2026-08-27/E2E-REAL-ENV-result-e9420ae.md`.

## Required invariants preserved

Odoo remains operational authority. Business capabilities use the originating effective user with `su=False`; ACLs, record rules, field access and company scope remain effective. `CapabilityDefinition` and the effective catalog remain authoritative. The existing prepare, preview, approval, revalidation, durable write barrier, PLAN execute, verification and recovery path is unchanged by the final slice.

No provider/API/RAG/router/tool selector, arbitrary SQL/Python/shell/sudo or generic ORM method surface was added.

## Existing real evidence

The last pre-convergence real ACTION evidence at `5995717` remains FAIL evidence. It is not converted into a PASS by automated tests or by this handoff. Its first missing boundary was the action proposal/staging boundary that E2E-3/E2E-4 were designed to replace with the host-owned decision loop and canonical plan proposal.

## Remaining validation debt

The exact-SHA standalone and Odoo test debts are closed. Remaining debt is:

- a deterministic Odoo regression for the primary-turn versus independent-event serialization
  collision;
- a bounded product correction that preserves the current host/capability/ACTION invariants;
- a retry-free real Codex one-decision round trip under the supported Odoo worker/account path;
- durable transcript persistence across real worker/process restart;
- clean real HELLO without a runtime requeue;
- real READ against a disposable known partner without serialization failure;
- real ACTION against a disposable partner through preview, one explicit approval, exactly one barrier/effect and verification;
- a final sanitized PASS record and fixture/database cleanup;
- broad Odoo/Codex account test isolation remains follow-up debt after this hard gate.

## Exact next action

Correct the turn/event serialization collision reproduced at `e9420ae80cf1d6a030312e5e4e76a911c60c7b18`.
Add an Odoo regression that keeps a primary turn transaction active while independent activity
events are persisted and proves that the final flush/commit does not fail or lose monotonic event
ordering. Do not weaken Odoo authority, `su=False`, transcript privacy, capability contracts,
approval, write barrier, verification, or recovery semantics.

After publishing the bounded product/test SHA, update `docs/research/E2E_REAL_ENV_HANDOFF.md` and
rerun its full standalone, Odoo, HELLO, READ and ACTION sequence in a fresh disposable database.
Do not claim the real gate passed until all criteria pass without hidden runtime retries.
