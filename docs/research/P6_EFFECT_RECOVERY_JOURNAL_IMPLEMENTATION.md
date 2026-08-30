# P6.4 / P6.6 effect recovery units and EffectJournal implementation

Date: 2026-08-30  
Status: **IMPLEMENTED_PENDING_PERIODIC_VALIDATION**  
Scope: P6.4 atomic/segmented recovery foundation + P6.6 short-TTL EffectJournal

This checkpoint builds on the provider-neutral P6.1/P6.3/P6.5 foundation. It does not mark any
Phase-6 real gate PASS.

## 1. Recovery model

`CapabilityPlanService` now prepares format-v3 EffectPlans with host-derived recovery metadata:

```text
step.recovery_unit_id
step.recovery_mode
step.journal_classification
plan.recovery_units[]
```

Supported recovery modes are:

```text
odoo_atomic
segmented
external
```

Current built-in Odoo-local PLAN capabilities default to `odoo_atomic`. Consecutive atomic steps are
grouped into one recovery unit and therefore still share one Odoo transaction after the durable
write barrier.

Trusted future capability definitions may explicitly declare `segmented` or `external` recovery
mode through bounded host-owned capability metadata. The model/provider cannot supply that metadata
as authority.

## 2. Durable segmented execution

For every recovery unit the host:

```text
preflight version/binding/dependencies/preconditions/approval
 -> mark unit executing in the durable plan
 -> acquire/reacquire the turn effect lock
 -> recheck Stop/redirect
 -> persist journal intent
 -> cross/retain the durable write barrier
 -> execute + verify the unit
 -> if another unit follows: persist completed unit + commit
 -> repeat
```

A checkpoint commit releases PostgreSQL transaction-scoped advisory locks, so the next unit
explicitly reacquires the turn effect lock before its final control-plane check.

The final unit remains in the worker transaction until the completed plan, verified receipt and final
journal state are written. Existing single-unit Odoo-local plans preserve the previous one-barrier
transaction behavior.

A persisted recovery unit already in `executing` state is not automatically replayed. That is a
recovery condition, not permission to try again.

## 3. Failure certainty

If the worker transaction fails after a unit was durably marked `executing`:

```text
odoo_atomic / segmented internal unit -> rolled_back
external unit                         -> uncertain
completed prior unit                  -> remains verified/durable
future prepared unit                  -> remains unexecuted/prepared
```

The existing turn failure state still becomes `recovery_required` after the write barrier. The new
journal supplies finer-grained unit certainty; it does not weaken the old no-blind-retry rule.

## 4. EffectJournal

New Odoo model:

```text
odoo.ai.effect.journal
```

Each row is bound to one durable turn + typed EffectPlan step and stores bounded host evidence:

```text
turn/user/company binding
recovery unit + mode
capability + version
classification + state
bounded before payload
bounded after payload
bounded verified receipt
expiry timestamp
```

Current hard limits:

```text
max rows per turn: 8
max JSON payload per journal section: 64 KiB
retention: 7 days
cleanup batch: 500 rows/day
```

Direct table access is restricted to system administrators. Normal users can request only the
sanitized journal projection for one turn they already own. The projection excludes raw before/after
snapshots and receipt payloads.

## 5. Classification

The journal uses:

```text
reversible
reconstructable
irreversible
external_or_unknown
```

`reversible` requires a structural HOST-only `<capability>.revert` compensator compatible with the
current internal-reversible capability. This currently covers supported patch/archive/unarchive
families.

`reconstructable` is deliberately weaker than reversible. Current generic create operations are
classified this way as a statement about bounded reconstruction evidence, never as an automatic
undo. Generic irreversible delete remains `irreversible`; no fake delete undo is introduced.
External/host effects are `external_or_unknown` unless a future trusted capability contract can make
a stronger host-verifiable claim.

## 6. Compensation integration

P5.8 compensation remains the only actual revert path for supported reversible effects. After a
verified compensation succeeds, matching journal rows move from `verified` to `reverted`.

The model never receives a new `revert` tool from the journal and cannot bypass current effective-user
ACL, optimistic conflict checks or compensator verification.

## 7. Browser/product projection

Prepared/completed plan responses now derive atomicity from recovery units instead of hardcoding
`is_atomic=True`.

Sanitized metadata includes:

```text
is_atomic
recovery_unit_count
has_segmented_effects
has_external_effect
```

Raw journal snapshots are not sent with the normal plan response.

## 8. Compatibility

Prepared plan formats v1/v2 remain accepted. At execution they are conservatively upgraded to
current host-derived recovery metadata. Existing effect steps and compensation plans keep their
capability/version/arguments/preview/result/verification shape.

No provider-specific recovery code was added. Codex remains below the neutral EffectPlan/runtime
contract.

## 9. Tests committed with the implementation

Focused coverage now includes:

```text
tests/e2e/test_phase6_effect_recovery_contract.py
addons/odoo_ai_assistant/tests/test_effect_journal.py
updated TestCanonicalPlanHostLoop format-v3/recovery assertions
```

The new coverage checks recovery-unit shape, no blind replay of in-flight units, lock/checkpoint
semantics, journal retention/bounds, conservative classification, owner isolation and internal-vs-
external failure certainty.

These tests are committed but the expensive full Odoo/HOOT/real batch is intentionally deferred to
`PERIODIC_FULL_REGRESSION_RUNBOOK.md` under the repository validation policy.

## 10. Accumulated periodic real debt

This checkpoint adds:

```text
P6-REAL-EFFECT-ATOMICITY
P6-REAL-SEGMENTED-RECOVERY
P6-REAL-EFFECT-JOURNAL
```

Existing pending Phase-6 debt remains:

```text
P6-REAL-MULTISTEP
P6-REAL-LOOP-BOUNDS
```

P6.2 adaptive/deliberate planning and `P6-REAL-REPLAN` remain a separate coherent product-planning
block and can be implemented before the next periodic expensive validation run.
