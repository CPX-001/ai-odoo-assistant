# P0-REAL-ACTION-V2 — real-environment result

Date: 2026-08-27
Commit materially tested: `59957173510ec7f5da6d0ac39e9ea52244dbba86`
Validation ID: `P0-REAL-ACTION-V2`
Gate: `HARD`
Result: **FAIL — PLAN TOOL NOT SELECTED**

## Deterministic validation completed first

The standalone Phase 0/action diagnostic suite passed after aligning three sanitizer expectations
with the intentional stable `diagnostic_code: null` field:

```text
30 passed in 0.24s
```

The targeted Odoo suites for planning contract, actions, action-policy revalidation, embedded
runtime, capability framework and batch mutations then passed in a fresh disposable database:

```text
odoo_ai_assistant: 44 tests
0 failed, 0 errors
```

A broader module test run also found one separate Codex account connect/disconnect test failure in
the fresh environment. It is configuration/test-isolation debt and was not on the ACTION planning,
preview or effect path.

## Real product-path result

The primary Odoo database was upgraded with the tested addon and the Odoo service restarted. A
dedicated temporary internal user with the strict profile requested one reversible field update on
a disposable partner through the authenticated HTTP product path.

Sanitized result:

```text
turn_state: completed
error_code: none
attempt_count: 1
write_barrier: false
plan_step_count: 0
reasoning_tool_count: 6
planning_tool_count: 6
staged_plan_count: 0
structured_plan_count: 0
final_plan_count: 0
final_plan_source: read_only
confidence: low
preview_observed: false
approval_observed: false
effect_count: 0
verification_observed: false
browser_final_ms: 19599.361
odoo_service_stable: true
```

No `tool.started` event occurred. The provider emitted its first answer delta and completed without
selecting a reasoning capability or the intended PLAN capability.

## Boundary diagnosis

```text
last successful boundary:
  planning_catalog_exposed(reasoning_tool_count=6, planning_tool_count=6)

first missing required boundary:
  plan_step_staged(capability=odoo.record.patch)

observed terminal boundary:
  final_plan_reconciled(
    source=read_only,
    staged_plan_count=0,
    structured_plan_count=0,
    final_plan_count=0
  )
```

The v2 staged-plan fallback was not exercised because no PLAN candidate was staged. Discovery,
preview, policy, approval, effect and verification cannot be blamed for this run: control never
reached them.

## Safety and cleanup

```text
record_unchanged: true
explicit_approval_observed: false
write_barrier_crossed: false
recovery_state_seen: false
temporary_user_archived: true
temporary_partner_archived: true
administrator_profile_restored: true
disposable_test_database_removed: true
odoo_service_active_after_cleanup: true
```

The temporary database was deliberately dropped after validation and is not recoverable; it
contained only disposable test state. No credentials, prompt, provider payload, tool arguments or
business values are published.

## Consequence

Phase 0 remains blocked. Repeating another prompt-only planning correction is not justified. The
next bounded correction is the host-owned iterative `NextDecision` loop specified in
`docs/research/E2E_AGENT_LOOP_CONVERGENCE.md`. It borrows Apexive's proven orchestration shape while
retaining the Assistant's authoritative capability/action lifecycle.
