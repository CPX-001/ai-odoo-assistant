# Stabilization execution state

State format: 2  
Updated: 2026-08-27  
Latest repository checkpoint inspected: `075138d7d9b519d46c60990ad465f06832d0bae8`  
Latest product/tooling implementation checkpoint: `075138d7d9b519d46c60990ad465f06832d0bae8`  
Latest P0 ACTION real checkpoint materially tested: `38c7c9a121cc797b9a2737fb312283506aa152f6`  
Roadmap: `FOUNDATION_STABILIZATION_PLAYBOOK.md`

## Current cursor

```text
phase: 0
phase_name: reproducible baseline
phase_state: BLOCKED
active_slice: P0-REAL-ACTION-plan-omission-correction
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

`P1-PREP-CONFORMANCE` is already COMPLETE. No additional Phase 1 look-ahead is authorized while the ACTION correction changes the provider planning contract for write/approval behavior.

## Processed real evidence

- P0.1/P0.2/P0.3/P0.4 corrective evidence remains complete.
- failure-pair matrix: PASS with five distinct paths.
- aggregate Phase 0 report remains `ready_for_phase1=false` because ACTION is absent.
- `P0-REAL-ACTION`: FAIL at `38c7c9a`; one real browser turn completed after three bounded tool pairs with no error, `write_barrier=false`, `plan_step_count=0`, no approval preview and no effect. The disposable record remained unchanged and Odoo service identity stayed stable.

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

## Validation debt

### VD-P0-LIVE-BASELINE

```text
validation_id: P0-REAL-ACTION
gate_type: HARD
origin_slice: Phase 0 minimum live matrix
commit_materially_tested: 38c7c9a121cc797b9a2737fb312283506aa152f6
downstream_scope_blocked:
  - completing Phase 0
  - Phase 1 production provider/runtime refactor
  - provider lifecycle optimization
reason: explicit supported partner mutation produced a completed zero-step plan with no approval preview
```

### VD-P0-ACTION-CORRECTION-LOCAL

```text
validation_id: P0-ACTION-CORRECTION-LOCAL
gate_type: HARD
origin_slice: P0-REAL-ACTION-plan-omission-correction
commit_materially_tested: pending
downstream_scope_blocked:
  - advancing the correction to real-environment validation
reason: the new Codex planning-contract test and relevant embedded-agent/action regressions have not been executed in an Odoo-capable local environment
```

### VD-P0-ACTION-CORRECTION-REAL

```text
validation_id: P0-REAL-ACTION-CORRECTED
gate_type: HARD
origin_slice: P0-REAL-ACTION-plan-omission-correction
commit_materially_tested: 075138d7d9b519d46c60990ad465f06832d0bae8
downstream_scope_blocked:
  - closing P0-REAL-ACTION
  - completing Phase 0
reason: corrected planning contract has not yet been validated in real Odoo 18 + authenticated Codex + browser
```

## Current blocker

```text
P0_ACTION_CORRECTION_VALIDATION_REQUIRED
```

## Exact next action

1. In an Odoo-capable local environment on `075138d7d9b519d46c60990ad465f06832d0bae8`, execute the targeted test module `addons/odoo_ai_assistant/tests/test_codex_planning_contract.py` plus the existing embedded-agent/action regression tests that cover planning catalog, preview, approval and revalidation. Record exact commands and results; do not claim PASS if the environment cannot run them.
2. If deterministic validation fails, repair only the correction slice and keep Phase 1 locked.
3. If deterministic validation passes, rerun one disposable `P0-REAL-ACTION-CORRECTED` through the normal browser -> Odoo 18 -> embedded runtime -> authenticated Codex path.
4. Require the explicit supported partner mutation to emit `odoo.record.patch` and reach the exact `awaiting_confirmation` preview while the record is still unchanged.
5. Approve exactly once; require exactly one business effect, host verification PASS, terminal completed state and stable Odoo service identity.
6. If that passes, create and reject the separate accepted `capture_kind=live_http` `write_preview` measurement capture, then rerun `phase0_report.py` and require `ready_for_phase1=true`.
7. Only after both validation debts close may Phase 0 become COMPLETE and Phase 1 production work begin.

## Publication policy

- No GitHub Actions.
- Unrun tests remain debt.
- Publish coherent checkpoints to `origin/main` without force-push.
- Never publish credentials, raw provider output, unsanitized business evidence or private reasoning.
