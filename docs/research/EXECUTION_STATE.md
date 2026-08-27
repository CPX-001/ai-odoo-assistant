# Stabilization execution state

State format: 2  
Updated: 2026-08-27  
Latest repository checkpoint inspected: `97617fefe40c22803a140b03023fd0df67594be1`<br>
Latest product/tooling implementation checkpoint: `075138d7d9b519d46c60990ad465f06832d0bae8`  
Latest P0 ACTION real checkpoint materially tested: `97617fefe40c22803a140b03023fd0df67594be1`<br>
Roadmap: `FOUNDATION_STABILIZATION_PLAYBOOK.md`

## Current cursor

```text
phase: 0
phase_name: reproducible baseline
phase_state: BLOCKED
active_slice: P0-REAL-ACTION-plan-omission-correction-v2
active_slice_state: BLOCKED
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

`P1-PREP-CONFORMANCE` is already COMPLETE. No additional Phase 1 look-ahead is authorized while the ACTION correction changes the provider planning contract for write/approval behavior.

## Processed real evidence

- P0.1/P0.2/P0.3/P0.4 corrective evidence remains complete.
- failure-pair matrix: PASS with five distinct paths.
- aggregate Phase 0 report remains `ready_for_phase1=false` because ACTION is absent.
- `P0-REAL-ACTION`: FAIL at `38c7c9a`; one real browser turn completed after three bounded tool pairs with no error, `write_barrier=false`, `plan_step_count=0`, no approval preview and no effect. The disposable record remained unchanged and Odoo service identity stayed stable.
- `P0-REAL-ACTION-CORRECTED`: FAIL at `97617fe`; after the planning-obligation correction,
  the real browser turn reproduced the same three bounded tool pairs and completed zero-step plan.
  No approval or effect occurred, the record remained unchanged and Odoo retained PID `75689`.

## Completed ACTION diagnosis slice

Evidence:
`docs/research/evidence/phase0/2026-08-27/P0-REAL-ACTION-zero-step-regression.md`

Static diagnosis established an acceptance gap:

- empty `AgentReasoningResult.plan` is structurally valid;
- provider-neutral plan validation accepts zero steps;
- Codex output schema requires `plan` but does not require at least one item;
- there is no independent host semantic fact proving a natural-language request requires a write.

The sanitized Phase 0 evaluator rejects a completed zero-step result when evidence is explicitly classified as `explicit_supported_write`.

Previously executed deterministic validation for that evaluator:

```text
python -m py_compile tests/e2e/phase0_action_acceptance.py
PASS

python -m pytest -q tests/unit/test_phase0_action_acceptance.py
3 passed in 0.06s
```

## Implemented ACTION correction checkpoint

Implementation checkpoint:
`075138d7d9b519d46c60990ad465f06832d0bae8`

The smallest provider/agent-contract correction was applied without adding a router or host-side prompt classifier:

- Codex base instructions now state that planning is an output obligation when the requested outcome is an Odoo state change exactly supported by an available planning capability;
- the provider must ground model/record/schema/fields/values through read-only capabilities before emitting the plan;
- `plan=[]` is explicitly documented as insufficient for an explicit supported mutation;
- inability/ambiguity still resolves to clarification or limitation, not an invented write;
- host authority is unchanged: effective planning catalog, schema, policy, preview/approval and verification remain authoritative;
- `test_codex_planning_contract.py` locks the instruction contract and verifies that `odoo.record.patch` is disclosed as a bounded PLAN/write/policy capability with the expected required arguments under `su=False`;
- `CAPABILITY_FRAMEWORK.md` now records the provider planning obligation and explicitly states that it is probabilistic model guidance, not host write-intent authority.

Repository-level diff inspection of `075138d7` confirms that the production change is limited to the Codex planning instructions; no executor, policy, approval, mutation, schema or verification code changed.

Executable Odoo tests were not runnable from the GitHub-only execution environment used for this checkpoint. They are therefore validation debt, not assumed PASS.

## Completed ACTION correction local validation

Validation checkpoint: `08564a9f93ebd890dc7238db91ab9f6d191b2502`.

The first Odoo run exposed that the new planning-contract module was absent from
`addons/odoo_ai_assistant/tests/__init__.py`, so Odoo had executed only the seven pre-existing
action/revalidation tests. After registering the module, the two new tests ran and exposed two
test defects: a whitespace-sensitive multiline instruction assertion and use of the superuser
record while asserting `su=False`. Both tests were corrected to normalize instruction whitespace
and use `base.user_admin` with `su=False`.

Actually executed validation:

```text
standalone Phase 0/provider suite: 39 passed in 0.14s

Odoo targeted planning/action/revalidation suite:
0 failed, 0 errors of 9 tests

Odoo embedded runtime/framework/batch suite:
0 failed, 0 errors of 20 tests
```

All Odoo suites ran against fresh disposable databases, which were dropped after each run. The
primary Odoo service and database were not used by those test runners.

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
reason: explicit supported partner mutation still produced a completed zero-step plan with no approval preview after the planning-obligation correction
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
reason: corrected planning contract was validated in real Odoo 18 + authenticated Codex + browser and did not change the zero-step outcome
```

## Current blocker

```text
P0_REAL_ACTION_CORRECTION_INSUFFICIENT_ZERO_STEP_PERSISTS
```

## Exact next action

1. Diagnose why the real Codex result still emits `plan=[]` after three successful bounded reads
   despite receiving the explicit planning-obligation contract. Use only sanitized provider/plan
   evidence; do not infer hidden reasoning.
2. Add a deterministic regression for the newly identified boundary before implementing a second
   correction. Do not add an unrestricted intent router or move write authority out of Odoo.
3. Implement the smallest bounded correction that preserves capability discovery, schema, policy,
   preview, approval, effective-user execution and verification invariants.
4. Rerun the local Odoo suites and then one disposable browser ACTION. Do not repeat the current
   browser request without a materially new correction.
5. Only after the ACTION passes, create/reject the separate `write_preview` capture and rerun
   `phase0_report.py` to require `ready_for_phase1=true`.

## Publication policy

- No GitHub Actions.
- Unrun tests remain debt.
- Publish coherent checkpoints to `origin/main` without force-push.
- Never publish credentials, raw provider output, unsanitized business evidence or private reasoning.
