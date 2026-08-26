# Execution slice template

Use this template when a roadmap item is large or important enough to need its own durable execution record.

A slice is a coherent change that can be implemented, validated as far as the current environment permits, documented and checkpointed without leaving `main` half-migrated.

---

# <slice id> — <title>

```text
phase:
state: PENDING | READY | IN_PROGRESS | LOCAL_VALIDATION_REQUIRED | REAL_ENV_VALIDATION_REQUIRED | BLOCKED | COMPLETE | SUPERSEDED
inspected_head:
gate_type: HARD | SOFT
lookahead_eligible: yes | no
```

## Objective

What concrete product/engineering behavior changes when this slice is complete?

## Why this slice exists

Describe the current observed problem and why it belongs in this slice rather than another layer.

## Prerequisites

List required completed slices, accepted ADRs, runtime facts and validation evidence.

Explicitly identify any unresolved validation debt.

## Dependency on unvalidated contracts

```text
depends_on_unvalidated_contracts:
  - none | <contract/slice>
creates_new_production_contract: yes | no
stacked_unvalidated_contract_layers_after_slice: <integer>
```

If the slice consumes an unvalidated new production contract, it is normally **not** eligible for look-ahead.

## Gate classification

### HARD

Use when failure of the pending validation could change the downstream design, security/authority semantics, provider protocol, recovery behavior or contract consumed by later slices.

A hard gate blocks dependent work.

### SOFT

Use when remaining validation may be batched and downstream work remains valid regardless of its outcome.

Explain why the gate is soft. Do not classify a gate soft merely because the real environment is inconvenient to access.

## Look-ahead justification

Complete only when `lookahead_eligible: yes`.

Answer:

1. Why will this work remain useful if the pending real validation fails?
2. Does it change production runtime behavior?
3. Does it consume a new unvalidated contract?
4. What validation debt does it create?
5. How much of the configured look-ahead budget does it consume?

If these answers are not clear, set `lookahead_eligible: no`.

## Likely affected areas

List files/modules/contracts to inspect, not a mandatory implementation patch.

## Invariants

At minimum consider as relevant:

- Odoo effective user and `su=False`;
- host-owned capability/schema/policy/approval/execution/verification;
- durable turn/recovery semantics;
- no arbitrary SQL/Python/shell/sudo/unrestricted ORM methods;
- no secret/raw reasoning leakage;
- embedded runtime constraints;
- no GitHub Actions dependency for this roadmap.

## Failure modes

List concrete ways the slice could regress behavior, including compatibility/restart/cancellation/write ambiguity where applicable.

## Implementation scope

What may be changed in this slice.

## Explicitly out of scope

What must not be pulled into this slice merely because it is nearby.

## Deterministic validation

List exact tests/checks that must run when the execution environment supports them.

Record results later as:

```text
command/check:
result: PASS | FAIL | NOT_RUN
commit:
notes:
```

`NOT_RUN` is not PASS.

## Real-environment validation

Reference IDs from `REAL_ENV_VALIDATION_PROTOCOL.md` or define new IDs there first.

```text
required_validation_ids:
  - ...
```

Record the exact commit materially tested.

## Validation debt created

For every pending validation:

```text
validation_id:
gate_type: HARD | SOFT
origin_slice:
commit_materially_tested: pending | <sha>
downstream_scope_blocked:
reason:
```

A slice may carry unresolved debt only within the limits in `CONTINUOUS_EXECUTION_PROTOCOL.md`.

## Exit criteria

A slice is `COMPLETE` only when its mandatory implementation, tests, required real validation for completion, documentation and cleanup are done.

If code is ready but live validation is pending, use `REAL_ENV_VALIDATION_REQUIRED`, not `COMPLETE`.

## Documentation/cleanup

Name current docs/ADRs to update and obsolete current-path code to remove if applicable.

## Result / discoveries

Fill during/after implementation. Record contradictions with the original plan and decisions made from new evidence.

## Next action

State exactly what the next independent run should do.

If the slice is waiting for validation, say whether an explicitly named look-ahead slice is allowed and why. Never leave a vague `continue` instruction.
