# Phase 0 ACTION diagnostic evidence contract

Status: current validation guidance for `P0-REAL-ACTION-plan-omission-correction-v2`.

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

For the v2 correction, a successful planning boundary is expected to show one `plan_step_staged` for the intended PLAN capability and then `final_plan_reconciled` with `final_plan_count >= 1`. The subsequent authoritative path is still `CapabilityPlanService.prepare -> preview -> policy/approval -> execute -> verify`.

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

## Validation order for v2

1. Run deterministic standalone tests, including ACTION acceptance and diagnostic-capture sanitizer tests.
2. Run targeted Odoo planning/action/revalidation tests plus embedded runtime/framework/batch tests.
3. Only after local PASS, run one disposable browser ACTION on the exact tested commit using the diagnostic capture.
4. Require correct preview while the record is unchanged.
5. Approve once; require exactly one effect and verification PASS.
6. If it fails, persist the sanitized boundary evidence above before attempting another correction.
7. Only after ACTION PASS should the separate `write_preview` capture and aggregate Phase 0 report be used to decide `ready_for_phase1`.
