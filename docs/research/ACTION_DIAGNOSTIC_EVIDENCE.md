# Phase 0 ACTION diagnostic evidence contract

Status: current validation guidance for `P0-E2E-host-loop-convergence` and the eventual ACTION rerun.

## Purpose

ACTION failures must leave enough **sanitized boundary evidence** to locate the failing layer without storing raw prompts, business data, capability arguments/results or provider internals.

Use `tests/e2e/phase0_live_diagnostic_capture.py` instead of the normal Phase 0 capture when diagnosing ACTION/provider-planning behavior. It reuses the same HTTP/product path but additionally preserves only:

- validated installed capability identifiers on `tool.*` events;
- bounded `diagnostic.planning` checkpoints;
- counts and source labels needed to distinguish staging, final structured output and reconciliation.

It does **not** preserve prompt/answer text, capability arguments/results, business values, credentials, stdout/stderr or private reasoning.

## Required ACTION result summary

Every real ACTION attempt for this gate should record at least:

```text
validation_id
commit_tested
turn_state
error_code
plan_state
plan_step_count
preview_observed
approval_required
record_unchanged_before_approval

tool sequence:
  <logical capability names in observed order>

planning diagnostics:
  planning_catalog_exposed(reasoning_tool_count, planning_tool_count)
  plan_step_staged(capability, staged_plan_count)              # when staging occurs
  plan_step_duplicate(...)                                    # only if observed
  final_plan_reconciled(structured_plan_count,
                        staged_plan_count,
                        final_plan_count,
                        source)
  or final_plan_rejected(...)

lifecycle counts:
  tool_started/tool_completed
  tool_preview_started/tool_preview_completed
  approval_required/approved/rejected
  execution_barrier
  tool_verify_started/completed/failed
  recovery_required

effect_count
service_identity_stable
```

The failed v2 run at `5995717` observed `planning_catalog_exposed(6, 6)` followed by
`final_plan_reconciled(source=read_only, staged=0, structured=0, final=0)`. No tool event occurred.
Its first missing boundary was `plan_step_staged(odoo.record.patch)`.

After the host-loop convergence, the equivalent successful planning boundary is one validated
`PlanStepProposal` for the intended PLAN capability. That host-observed proposal is canonical and
must feed the unchanged capability-plan prepare/preview/policy/approval/execute/verify path; it
must not depend on a duplicated final `plan=[]` serialization.

## Failure reporting rule

Do not report only `ACTION failed` or only aggregate event counts. Record the **last successful boundary** and the **first missing/rejected boundary**.

Examples:

```text
last_successful_boundary: odoo.get_effective_write_schema completed
first_missing_boundary: plan_step_staged
```

or:

```text
last_successful_boundary: plan_step_staged(odoo.record.patch)
first_rejected_boundary: final_plan_rejected(source=plan_conflict)
```

This is diagnostic metadata, not model reasoning.

## Safety rule

Never commit or copy into roadmap evidence:

- message/system/developer prompt text;
- assistant answer text when it contains business content;
- tool/capability arguments or results;
- record field values beyond boolean/count acceptance facts;
- credentials/auth files/tokens;
- raw Codex protocol frames;
- provider stdout/stderr;
- hidden reasoning or chain-of-thought.

Capability names are installed-code identifiers and are allowed. Counts, state names, normalized error codes, timings and content-free planning source labels are allowed.

## Validation order for the next ACTION

1. Complete and validate E2E-0 through E2E-3 from `E2E_AGENT_LOOP_CONVERGENCE.md`, including real hello/READ parity.
2. Implement E2E-4 so one validated `PlanStepProposal` is canonical and stage-only.
3. Run deterministic ACTION/diagnostic tests and targeted Odoo planning/action/revalidation/runtime tests.
4. Only after local PASS, run one disposable browser ACTION on the exact tested commit using the diagnostic capture.
5. Require correct preview while the record is unchanged.
6. Approve once; require exactly one effect and verification PASS.
7. If it fails, persist the sanitized boundary evidence above before attempting another correction.
8. Only after ACTION PASS should the separate `write_preview` capture and aggregate Phase 0 report be used to decide `ready_for_phase1`.
