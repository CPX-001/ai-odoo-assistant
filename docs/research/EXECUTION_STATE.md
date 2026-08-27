# Stabilization execution state

State format: 2  
Updated: 2026-08-27  
Latest repository checkpoint inspected: `e8431c7709d09e869faec9df6398a86461a272e2`  
Latest product/tooling implementation checkpoint: `e8431c7709d09e869faec9df6398a86461a272e2`  
Latest P0 ACTION real checkpoint materially tested: `97617fefe40c22803a140b03023fd0df67594be1`  
Roadmap: `FOUNDATION_STABILIZATION_PLAYBOOK.md`

## Current cursor

```text
phase: 0
phase_name: reproducible baseline
phase_state: BLOCKED
active_slice: P0-REAL-ACTION-plan-omission-correction-v2
active_slice_state: LOCAL_VALIDATION_REQUIRED
current_gate_type: HARD
next_phase: 1
```

Phase 1 production provider/runtime architecture remains locked.

## Look-ahead budget

```text
max_phase_distance_ahead: 1
max_unvalidated_implementation_slices: 2
max_stacked_unvalidated_contract_layers: 1
currently_consumed_implementation_slices: 1
currently_stacked_unvalidated_contract_layers: 1
```

`P1-PREP-CONFORMANCE` is already COMPLETE. No additional Phase 1 look-ahead is authorized while the ACTION planning/output correction is unvalidated.

## Processed real evidence

- P0.1/P0.2/P0.3/P0.4 corrective evidence remains complete.
- failure-pair matrix: PASS with five distinct paths.
- aggregate Phase 0 report remains `ready_for_phase1=false` because ACTION is absent.
- `P0-REAL-ACTION`: FAIL at `38c7c9a`; one real browser turn completed after three bounded tool pairs with no error, `write_barrier=false`, `plan_step_count=0`, no approval preview and no effect. The disposable record remained unchanged and Odoo service identity stayed stable.
- `P0-REAL-ACTION-CORRECTED`: FAIL at `97617fe`; after the first planning-obligation correction, the real browser turn reproduced the same three bounded tool pairs and completed zero-step plan. No approval or effect occurred, the record remained unchanged and Odoo retained PID `75689`.

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

These new tests have **not yet been executed in an Odoo-capable environment**. They are validation debt, not assumed PASS.

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

### VD-P0-ACTION-V2-LOCAL

```text
validation_id: P0-ACTION-V2-LOCAL
gate_type: HARD
origin_slice: P0-REAL-ACTION-plan-omission-correction-v2
commit_materially_tested: e8431c7709d09e869faec9df6398a86461a272e2
downstream_scope_blocked:
  - P0-REAL-ACTION-V2
  - closing P0-REAL-ACTION
  - completing Phase 0
reason: materially new stage-only planning boundary and diagnostics have not yet run in the local/Odoo test environment
```

## Current blocker

```text
P0_ACTION_V2_LOCAL_VALIDATION_REQUIRED
```

## Exact next action

1. Pull the current main containing `e8431c7709d09e869faec9df6398a86461a272e2` and run the standalone Phase 0/action acceptance suite, including the new diagnostic sanitizer tests.
2. Run the targeted Odoo planning/action/revalidation suite and the embedded runtime/framework/batch suite on fresh disposable databases.
3. If any deterministic test fails, fix that failure before touching the real ACTION gate and record the exact failure.
4. Only after local PASS, restart/update the real Odoo 18 addon on that exact tested code and run **one** disposable browser ACTION through the normal product path using `phase0_live_diagnostic_capture.py`.
5. Require: intended PLAN capability staged, final plan count >= 1, exact preview, record unchanged before approval, approval required, exactly one approval, exactly one effect, verification PASS, terminal success and stable Odoo service identity.
6. If the real ACTION fails, record the safe tool sequence and `diagnostic.planning` checkpoints plus last-successful/first-missing boundary before making another correction. Do not repeat a vague zero-step report.
7. Only after ACTION PASS, create/reject the separate `write_preview` capture and rerun `phase0_report.py`; Phase 1 remains locked until `ready_for_phase1=true`.

## Publication policy

- No GitHub Actions.
- Unrun tests remain debt.
- Publish coherent checkpoints to `origin/main` without force-push.
- Never publish credentials, raw provider output, unsanitized business evidence or private reasoning.
