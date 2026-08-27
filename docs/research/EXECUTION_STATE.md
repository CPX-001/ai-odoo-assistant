# Stabilization execution state

State format: 3
Updated: 2026-08-27
Roadmaps: `FOUNDATION_STABILIZATION_PLAYBOOK.md` and `E2E_AGENT_LOOP_CONVERGENCE.md`

## Current cursor

```text
phase: 0
phase_name: reproducible baseline
phase_state: COMPLETE
active_slice: P0-E2E-host-loop-convergence
active_slice_state: COMPLETE
current_gate_type: NONE
next_phase: 1
```

The implementation/convergence work through E2E-4, its automated battery, the Codex one-decision
adapter correction and the turn/event transaction correction are complete. The full real Odoo +
Codex + browser HELLO -> READ -> ACTION gate passed, the disposable environment was removed and the
aggregate Phase 0 report returned `ready_for_phase1=true`.

## Exact implementation/test SHA

```text
9f832af4d6b1e6b74659bcd30aab21db481fd4b9
```

Commits after that SHA in this close-out are documentation-only.
`docs/research/E2E_REAL_ENV_HANDOFF.md` is the authoritative validation record/procedure.

## Published convergence checkpoints

- E2E-0: decision-sequence fixtures and explicit provider/capability/byte budgets.
- E2E-1: strict provider-neutral `NextDecision`, tool-free one-decision Codex adapter and host-side validation/revalidation.
- E2E-2: ADR-019 plus bounded private durable `working_items_payload`.
- E2E-3: active Odoo-owned iterative READ loop with REASONING-only execution, bounded correction, cancellation and restart/idempotency handling.
- E2E-4: one validated `PlanStepProposal` is canonical and stage-only. It feeds `CapabilityPlanService.prepare`; preview/approval/revalidation/write barrier/execute/verify/recovery remain authoritative and a verified private receipt is persisted with the effect result.
- E2E-final: added the aggregate 12-case dependency-light battery and an executable Odoo `TransactionCase` battery covering hello, READ, multi-read, patch, create, repairable errors, access denied, unsupported action, restart/idempotency, approval, exactly-once and verification. The focused canonical PLAN tests are now registered in the addon test suite.
- E2E-real-adapter repair: the one-decision Codex adapter now translates the strict provider-neutral union into an App Server-compatible Structured Outputs envelope, decodes bounded `arguments_json` back into the unchanged contract, and preserves `codex_output_schema_invalid` for the observed rejection.
- E2E-turn/event repair: private reasoning checkpoints and the ACTION pre-effect barrier now commit pending turn/event/transcript state on the primary worker cursor, eliminating the competing-row update that caused PostgreSQL `SerializationFailure` while preserving the pre-effect barrier.

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

The bounded correction at `9f832af4d6b1e6b74659bcd30aab21db481fd4b9` was then validated from a
fresh disposable Odoo database:

```text
git diff and Python compilation: PASS
standalone convergence: 12/12 PASS
decision sequences: 4/4 PASS
NextDecision: 4/4 PASS
working transcript: 4/4 PASS
canonical plan: 5/5 PASS
fresh addon install: PASS
targeted Odoo checkpoint regression: PASS
combined Odoo queue/runtime/convergence/PLAN/adapter/capability/action suites:
  38 tests, 0 failed, 0 errors
real HELLO: PASS, first claim, no diagnostic/requeue
real READ: PASS, bounded schema correction, no runtime/database retry
real ACTION: PASS, exact preview, record unchanged, one approval, one barrier/effect, verification
preview-only aggregate member: PASS and rejected without execution
phase0_report.py: exit 0, ready_for_phase1=true
fixture/database cleanup: PASS; Odoo left active
```

The authoritative ACTION used the user-visible `strict` autonomy profile. A preliminary inspection
showed that the existing `balanced` preference legitimately auto-authorized a moderate reversible
patch; the fixture was restored before the authoritative strict run. Prompt wording was not treated
as a substitute for host approval policy. See
`docs/research/evidence/phase0/2026-08-27/E2E-REAL-ENV-result-9f832af.md`.

## Required invariants preserved

Odoo remains operational authority. Business capabilities use the originating effective user with
`su=False`; ACLs, record rules, field access and company scope remain effective.
`CapabilityDefinition` and the effective catalog remain authoritative. Prepare, preview, approval,
revalidation, durable write barrier, PLAN execution, verification and recovery remain the existing
host-owned lifecycle. The correction changes only which worker cursor commits pre-effect turn
metadata; it does not move business authority or expose model-controlled execution.

No provider/API/RAG/router/tool selector, arbitrary SQL/Python/shell/sudo or generic ORM method surface was added.

## Existing real evidence

The pre-convergence ACTION evidence at `5995717` and the failed exact-SHA evidence at `e9420ae`
remain historical FAIL records; they are not rewritten. The new `9f832af` evidence is a separate
PASS after the bounded corrections.

## Remaining validation debt

All mandatory Phase 0 hard-gate debt is closed. Follow-up debt that does not reopen Phase 0:

- exercise durable transcript resumption across a real worker/process restart as part of the
  provider/lifecycle hardening suites;
- isolate the broad Codex account connect/disconnect test so full-module runs do not depend on
  shared installation account state;
- run the Phase 1 provider conformance bindings and the required repeated hello/simple-read soak
  before Phase 1 is marked complete.

## Exact next action

Begin Phase 1 at the provider boundary. Bind the existing custom Codex App Server adapter to the
already-prepared adapter-neutral conformance harness, then define/confirm the smallest
`ReasoningProvider` port required by the current host. Do not add another provider or replace the
adapter until the conformance spike compares the required safety and protocol behavior. Preserve
Odoo authority, `su=False`, capability contracts and the validated ACTION lifecycle.
