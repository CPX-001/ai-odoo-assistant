# P0-REAL-ACTION — failed real-environment attempt

Date: 2026-08-27<br>
Commit tested: `38c7c9a121cc797b9a2737fb312283506aa152f6`<br>
Validation ID: `P0-REAL-ACTION`<br>
Gate: `HARD`<br>
Result: **FAIL**

## Environment

- Odoo: 18.0 Community.
- Addon: `18.0.10.4.6`.
- Codex CLI: `0.144.2` (configured authenticated runtime).
- Browser: headless Chrome 151 through Playwright.
- User: dedicated temporary internal user with the strict / `always_confirm` profile.
- Fixture: disposable `res.partner`; one reversible `phone` change requested.

## Executed validation

The real Assistant panel was opened on the disposable partner and exactly one field update was
requested. The harness waited 240 seconds for the normal `awaiting_confirmation` UI. No approval
was sent because the required preview never appeared.

Persisted Odoo evidence after the wait showed:

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
```

The model used bounded tools but returned a completed zero-step plan instead of the requested
write proposal. This is a product-path failure for the Phase 0 ACTION gate: a terminal completed
turn is not evidence that the requested action was prepared or executed.

## Safety and cleanup

```text
preview_observed: false
explicit_approval_observed: false
effect_count: 0
verification_result: not_run
record_unchanged: true
recovery_state_seen: false
odoo_service_stable: true
service_pid_before: 48230
service_pid_after: 48230
fixture_restored: true
temporary_user_archived: true
temporary_partner_archived: true
```

No prompt, credentials, provider payload, tool arguments/results or business values are included
in this evidence.

## Deterministic regression

The relevant standalone Phase 0 suite ran before the live attempt:

```text
python -m pytest -q tests/unit/test_phase0_*.py tests/unit/test_codex_provider_conformance.py
33 passed in 0.18s
```

## Gate consequence

The separate `write_preview` capture and aggregate report were intentionally not run. The
authoritative browser ACTION had already hit an immediate FAIL/stop condition, and creating a
second write proposal could not repair that failure.

```text
phase0_report_exit: not_run_after_action_failure
ready_for_phase1: false
phase0_state: BLOCKED
blocker: P0_REAL_ACTION_PREVIEW_MISSING_ZERO_STEP_PLAN
```

Phase 1 remains locked. The next execution must diagnose why a direct, screen-scoped partner
update becomes a completed zero-step plan; it must not simply approve or repeat an ambiguous turn.
