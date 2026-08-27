# P0-REAL-ACTION-CORRECTED — failed real-environment attempt

Date: 2026-08-27<br>
Commit tested: `97617fefe40c22803a140b03023fd0df67594be1`<br>
Product correction: `075138d7d9b519d46c60990ad465f06832d0bae8`<br>
Validation ID: `P0-REAL-ACTION-CORRECTED`<br>
Gate: `HARD`<br>
Result: **FAIL**

## Local validation completed first

The new planning-contract test was initially not imported by Odoo. Checkpoint
`08564a9f93ebd890dc7238db91ab9f6d191b2502` registers it, normalizes the multiline instruction
assertion and executes the catalog check with `base.user_admin` under `su=False`.

Actually executed results:

```text
standalone Phase 0/provider suite: 39 passed in 0.14s
Odoo planning/action/revalidation: 9 passed, 0 failed, 0 errors
Odoo embedded runtime/framework/batch: 20 passed, 0 failed, 0 errors
```

The Odoo suites ran in fresh disposable databases and did not touch the primary database.

## Real browser result

The primary Odoo service was restarted on the corrected code and retained PID `75689` throughout
the measured turn. A dedicated temporary internal user used the strict / `always_confirm` policy
on a disposable partner. The real Assistant panel requested exactly one reversible `phone`
update.

The turn again ended as a normal completed read-only response instead of producing an approval
preview:

```text
turn_state: completed
error_code: none
attempt_count: 1
write_barrier: false
plan_state: completed
plan_step_count: 0
tool_started: 3
tool_completed: 3
approval_approved: 0
execution_barrier: 0
tool_verify_started: 0
recovery_required: 0
```

The planning-instruction correction therefore did not change the observed integrated behavior.
No approval was sent and no effect or verification ran.

## Acceptance evaluation

The sanitized evidence was evaluated by `tests/e2e/phase0_action_acceptance.py`. Expected exit
status `2` was observed with:

```text
accepted: false
reasons:
  - action_plan_missing
  - approval_preview_missing
  - approval_not_required
```

Artifacts:

- `p0-real-action-corrected-97617fe.json`
- `p0-real-action-corrected-97617fe-acceptance.json`

## Safety and cleanup

```text
record_unchanged: true
effect_count: 0
explicit_approval_observed: false
recovery_state_seen: false
odoo_service_stable: true
service_pid_before: 75689
service_pid_after: 75689
fixture_restored: true
temporary_user_archived: true
temporary_partner_archived: true
```

No prompt, credentials, provider payload, tool arguments/results or business values are included.

## Gate consequence

The separate `write_preview` measurement and aggregate report were intentionally not run after the
authoritative ACTION failed. Phase 0 remains blocked and Phase 1 remains locked.

```text
phase0_report_exit: not_run_after_action_failure
ready_for_phase1: false
blocker: P0_REAL_ACTION_CORRECTION_INSUFFICIENT_ZERO_STEP_PERSISTS
```

The next slice must diagnose why the provider still returns `plan=[]` after the explicit planning
obligation. Repeating the same browser request without a new bounded correction is not valid.
