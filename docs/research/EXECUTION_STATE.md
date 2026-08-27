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

The last check used the real installed App Server and an authenticated local provider home, but it
does not replace an exact-SHA product-path HELLO under the Odoo worker/account environment.

## Required invariants preserved

Odoo remains operational authority. Business capabilities use the originating effective user with `su=False`; ACLs, record rules, field access and company scope remain effective. `CapabilityDefinition` and the effective catalog remain authoritative. The existing prepare, preview, approval, revalidation, durable write barrier, PLAN execute, verification and recovery path is unchanged by the final slice.

No provider/API/RAG/router/tool selector, arbitrary SQL/Python/shell/sudo or generic ORM method surface was added.

## Existing real evidence

The last pre-convergence real ACTION evidence at `5995717` remains FAIL evidence. It is not converted into a PASS by automated tests or by this handoff. Its first missing boundary was the action proposal/staging boundary that E2E-3/E2E-4 were designed to replace with the host-owned decision loop and canonical plan proposal.

## Remaining validation debt

All remaining items are exact-SHA real-environment validation, not speculative implementation:

- exact-SHA standalone rerun from a real checkout;
- Odoo addon install/update and `TransactionCase` battery;
- real Codex one-decision round trip under the supported Odoo worker/account path;
- durable transcript persistence across real worker/process restart;
- real HELLO;
- real READ against a disposable known partner;
- real ACTION against a disposable partner through preview, one explicit approval, exactly one barrier/effect and verification;
- sanitized evidence and fixture/database cleanup;
- broad Odoo/Codex account test isolation remains follow-up debt after this hard gate.

## Exact next action

Follow `docs/research/E2E_REAL_ENV_HANDOFF.md` against implementation/test SHA `e9420ae80cf1d6a030312e5e4e76a911c60c7b18` on a disposable Odoo 18/WSL2 validation database. Begin with the adapter regression and real HELLO; continue to READ/ACTION only after HELLO passes.

Do not claim `REAL_ENV_VALIDATION_REQUIRED` has passed until the handoff's standalone, Odoo test, HELLO, READ and ACTION criteria all pass. On failure, record the first failing boundary and return to implementation only if the evidence proves a product/test defect.
