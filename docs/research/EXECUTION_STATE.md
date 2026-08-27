# Stabilization execution state

State format: 2  
Updated: 2026-08-27  
Latest repository checkpoint inspected: `4b5d510e6f8a61e9d2378b0bb00c678f95b67b4e`
Latest product/tooling implementation checkpoint: `4b5d510e6f8a61e9d2378b0bb00c678f95b67b4e`
Latest P0 ACTION real checkpoint materially tested: `59957173510ec7f5da6d0ac39e9ea52244dbba86`
Roadmaps: `FOUNDATION_STABILIZATION_PLAYBOOK.md` and `E2E_AGENT_LOOP_CONVERGENCE.md`

## Current cursor

```text
phase: 0
phase_name: reproducible baseline
phase_state: BLOCKED
active_slice: P0-E2E-host-loop-convergence
active_slice_state: DESIGN_COMPLETE_IMPLEMENTATION_REQUIRED
current_gate_type: HARD
next_phase: 1
```

General Phase 1 work remains locked. A narrow host-loop correction is authorized inside Phase 0
because the real v2 evidence disproved the assumption that another prompt-only correction could
close ACTION.

## Look-ahead budget

```text
max_phase_distance_ahead: 1
max_unvalidated_implementation_slices: 2
max_stacked_unvalidated_contract_layers: 1
currently_consumed_implementation_slices: 0
currently_stacked_unvalidated_contract_layers: 0
```

`P1-PREP-CONFORMANCE` is already COMPLETE. Only E2E-0 and then E2E-1 from
`E2E_AGENT_LOOP_CONVERGENCE.md` are authorized; no unrelated Phase 1 look-ahead is authorized.

## Processed real evidence

- P0.1/P0.2/P0.3/P0.4 corrective evidence remains complete.
- failure-pair matrix: PASS with five distinct paths.
- aggregate Phase 0 report remains `ready_for_phase1=false` because ACTION is absent.
- `P0-REAL-ACTION`: FAIL at `38c7c9a`; one real browser turn completed after three bounded tool pairs with no error, `write_barrier=false`, `plan_step_count=0`, no approval preview and no effect. The disposable record remained unchanged and Odoo service identity stayed stable.
- `P0-REAL-ACTION-CORRECTED`: FAIL at `97617fe`; after the first planning-obligation correction, the real browser turn reproduced the same three bounded tool pairs and completed zero-step plan. No approval or effect occurred, the record remained unchanged and Odoo retained PID `75689`.
- `P0-REAL-ACTION-V2`: FAIL at `5995717`; six reasoning and six planning tools were exposed, but Codex selected no tool and staged no plan step. The turn completed read-only with low confidence, zero plan steps, no preview and no effect. Odoo remained stable and the disposable fixture remained unchanged.

## Completed ACTION diagnosis

Evidence:
`docs/research/evidence/phase0/2026-08-27/P0-REAL-ACTION-zero-step-regression.md`

Static diagnosis first established that an empty provider plan was structurally valid and that no host-side natural-language write-intent fact existed. The first prompt-level correction at `075138d7d9b519d46c60990ad465f06832d0bae8` made supported mutation planning an explicit provider instruction without adding a router or moving authority out of Odoo.

That correction passed executable local validation:

```text
standalone Phase 0/provider suite: 39 passed in 0.14s
Odoo targeted planning/action/revalidation suite: 0 failed, 0 errors of 9 tests
Odoo embedded runtime/framework/batch suite: 0 failed, 0 errors of 20 tests
```

The real browser rerun nevertheless remained zero-step.

## Completed v2 capability trace diagnosis

Evidence:
`docs/research/evidence/phase0/2026-08-27/P0-REAL-ACTION-v2-capability-sequence.md`

The persisted failed turn proved this exact sequence completed successfully:

```text
odoo.get_effective_schema
odoo.get_effective_write_schema
odoo.query_records
```

Therefore bounded write preparation did run. The failure was narrowed to:

```text
prepared supported mutation -> final provider result plan=[]
```

The v2 correction must target that provider planning/output boundary rather than discovery, write schema, policy, preview or execution.

## Implemented ACTION v2 correction

Implementation checkpoint:
`e8431c7709d09e869faec9df6398a86461a272e2`

The Codex adapter now derives **stage-only dynamic tools** from the same effective PLAN catalog already owned by `CapabilityRegistry`.

Properties of the correction:

- PLAN definitions remain `CapabilityDefinition` instances from the effective host catalog; no second tool registry was introduced;
- a stage-only call validates the candidate arguments against the PLAN capability input schema and records a `PlannedCapability` candidate;
- staging never invokes the capability handler, never previews, never approves and never mutates Odoo;
- normal read-only reasoning tools still execute only under `ExecutionAuthority.REASONING`;
- after provider completion, one unambiguous staged candidate can recover an accidentally empty structured `plan=[]`;
- a staged/structured mismatch fails closed with `codex_plan_output_mismatch`;
- multiple staged steps with an empty structured plan fail closed as ambiguous rather than guessing ordering/intent;
- once a final plan exists, the unchanged authoritative path is still `CapabilityPlanService.prepare -> preview -> current policy/approval -> execute under effective user -> verify`;
- no natural-language host intent classifier, arbitrary ORM method, SQL/Python/shell/sudo path or approval bypass was added.

The provider also emits bounded `diagnostic.planning` metadata such as catalog counts, staged capability identifier/count and final reconciliation source/counts. It never emits plan arguments, results, prompts, business values or private reasoning in those diagnostics.

Deterministic tests were added/extended to cover:

- PLAN capability projection as a stage-only dynamic tool derived from the effective catalog;
- stage-only tool validation and the invariant that it does not execute the underlying capability;
- `single staged plan + final plan=[] -> staged fallback`;
- conflicting staged and structured plans -> fail closed;
- sanitized ACTION reports may carry validated capability identifiers and bounded planning diagnostics while dropping arbitrary content.

These tests were executed on 2026-08-27. The relevant standalone suite passed 30/30, and the
targeted Odoo planning/action/runtime/capability suites passed 44 tests with zero failures or
errors. A separate full-module run exposed one account connect/disconnect test-isolation failure;
that remains separate debt and does not invalidate the ACTION-specific suites.

## Real ACTION v2 result and architecture conclusion

Evidence:
`docs/research/evidence/phase0/2026-08-27/P0-REAL-ACTION-v2-result-5995717.md`

The real run closed the v2 local validation debt but failed the hard product gate. Its last
successful boundary was:

```text
planning_catalog_exposed(reasoning_tool_count=6, planning_tool_count=6)
```

Its first missing required boundary was:

```text
plan_step_staged(capability=odoo.record.patch)
```

The terminal reconciliation was `source=read_only`, `staged_plan_count=0`,
`structured_plan_count=0`, `final_plan_count=0`. No capability call occurred. The staged fallback
was therefore not reached.

The next correction is no longer another provider-instruction tweak. The approved research
direction is the Apexive-inspired, Odoo-owned iterative `NextDecision` loop in
`E2E_AGENT_LOOP_CONVERGENCE.md`. It keeps the current UI and authoritative action lifecycle.

## Improved ACTION diagnostic evidence

Current guidance:
`docs/research/ACTION_DIAGNOSTIC_EVIDENCE.md`

Use `tests/e2e/phase0_live_diagnostic_capture.py` for the next ACTION validation. It reuses the current Phase 0 HTTP capture but preserves additional content-free evidence:

- logical capability identifier on `tool.*` events;
- `diagnostic.planning` point/capability/count/source fields only.

A failed ACTION must record the last successful boundary and first missing/rejected boundary. Reports that contain only aggregate tool counts are no longer sufficient for this gate.

## Validation debt

### VD-P0-LIVE-BASELINE

```text
validation_id: P0-REAL-ACTION
gate_type: HARD
origin_slice: Phase 0 minimum live matrix
commit_materially_tested: 97617fefe40c22803a140b03023fd0df67594be1
downstream_scope_blocked:
  - completing Phase 0
  - Phase 1 production provider/runtime refactor
  - provider lifecycle optimization
reason: explicit supported partner mutation still produced a completed zero-step plan with no approval preview at the last real checkpoint
```

### VD-P0-ACTION-CORRECTION-REAL

```text
validation_id: P0-REAL-ACTION-CORRECTED
gate_type: HARD
origin_slice: P0-REAL-ACTION-plan-omission-correction
commit_materially_tested: 97617fefe40c22803a140b03023fd0df67594be1
downstream_scope_blocked:
  - closing P0-REAL-ACTION
  - completing Phase 0
reason: first corrected planning contract was validated in real Odoo 18 + authenticated Codex + browser and did not change the zero-step outcome
```

### VD-P0-ACTION-V2-REAL

```text
validation_id: P0-REAL-ACTION-V2
gate_type: HARD
origin_slice: P0-REAL-ACTION-plan-omission-correction-v2
commit_materially_tested: 59957173510ec7f5da6d0ac39e9ea52244dbba86
downstream_scope_blocked:
  - closing P0-REAL-ACTION
  - completing Phase 0
reason: effective PLAN catalog was exposed, but Codex selected no tool and staged no action proposal
```

### VD-ACCOUNT-TEST-ISOLATION

```text
validation_id: ODOO-CODEX-ACCOUNT-TEST-ISOLATION
gate_type: SOFT for E2E-0; HARD before broad module regression is claimed green
origin_slice: P0-ACTION-V2 local validation
observed_in: fresh disposable full-module test run
reason: TestEmbeddedCodexAccount connect/disconnect expectation failed while all targeted ACTION suites passed
```

## Current blocker

```text
P0_ACTION_PROVIDER_CONTROL_LOOP_REQUIRED
```

## Exact next action

1. Implement E2E-0 only: table-driven decision-sequence evals and explicit provider/capability/byte budgets for hello, read, multi-read, patch, create, repair, denial and unsupported action.
2. Validate E2E-0 without changing runtime behavior; record actual standalone and Odoo results.
3. If E2E-0 passes, implement E2E-1: the strict provider-neutral `NextDecision` union and one-decision Codex structured-output adapter, using local `llm_codex` as behavioral reference only.
4. Do not implement the durable transcript or host loop in the same unvalidated slice.
5. After E2E-1 deterministic conformance passes, advance in order through E2E-2 and E2E-3. Revalidate real hello/READ before routing PLAN.
6. Implement E2E-4 by making one validated `PlanStepProposal` canonical and feeding it into the unchanged `CapabilityPlanService.prepare` lifecycle.
7. Then run one disposable real ACTION. Require exact preview, unchanged pre-approval record, one approval, exactly one verified effect, stable Odoo and fixture restoration.
8. Only after ACTION PASS, create/reject the separate `write_preview` capture and rerun `phase0_report.py`; later phases remain locked until `ready_for_phase1=true`.

## Publication policy

- No GitHub Actions.
- Unrun tests remain debt.
- Publish coherent checkpoints to `origin/main` without force-push.
- Never publish credentials, raw provider output, unsanitized business evidence or private reasoning.
