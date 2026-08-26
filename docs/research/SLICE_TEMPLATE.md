# Slice template

Use this template for a roadmap slice that needs its own execution record. Remove guidance comments when instantiating it.

```text
slice_id:
phase:
status: PENDING | READY | IN_PROGRESS | LOCAL_VALIDATION_REQUIRED | REAL_ENV_VALIDATION_REQUIRED | BLOCKED | COMPLETE | SUPERSEDED
inspected_head:
started_at:
completed_at:
```

## Objective

State one observable product/engineering outcome. Avoid implementation-first wording when possible.

## Why this slice exists

Link the parent playbook/phase problem and any concrete regression/evidence that makes this work necessary.

## Inspected baseline

List the current files/classes/contracts/tests actually inspected before writing.

## Prerequisites

- [ ] parent slices complete;
- [ ] required ADR/decision exists;
- [ ] required fixtures/environment available.

## Invariants

Explicitly list relevant invariants, normally including Odoo effective-user authority, host-owned capability validation, approval/verification for writes, durable turn semantics and no unsafe generic execution surface.

## Scope

What this slice is allowed to change.

## Out of scope

Name tempting adjacent changes that should not be pulled into the slice.

## Proposed change

Describe contract/behavior changes, not private reasoning.

## Failure modes to cover

List concrete failure modes introduced/affected by the slice.

## Deterministic validation

Tests that must actually run before the slice can complete.

```text
command/test:
expected:
result: NOT_RUN | PASS | FAIL
execution_environment:
```

Do not mark `PASS` from code inspection alone.

## Real Odoo + Codex validation

Reference validation IDs from `REAL_ENV_VALIDATION_PROTOCOL.md` or define new IDs here.

```text
validation_id:
required_before: slice_complete | phase_exit | optional
result: NOT_RUN | PASS | FAIL | BLOCKED
commit_tested:
```

If no live validation is required, explain why deterministic evidence is sufficient.

## Documentation/cleanup

Current docs/ADRs to update when behavior becomes real; obsolete code to remove.

## Exit criteria

- [ ] implementation coherent;
- [ ] deterministic tests actually passed;
- [ ] mandatory real validations passed;
- [ ] docs updated;
- [ ] no unresolved safety/recovery blocker;
- [ ] `EXECUTION_STATE.md` advanced.

## Execution log

Record concise discoveries/decisions/results by commit. Do not use this as chain-of-thought.

## Next slice

State exactly what becomes `READY` after this slice closes.