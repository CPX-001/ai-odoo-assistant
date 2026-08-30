# Stabilization execution state

State format: 38
Updated: 2026-08-30

Accepted lineage:

```text
P0-P4 through 8a4432dc9852eacc422b8c794b6613c75da702a9
P5.1 through f7f924ce944db86e896745fef83ea2fb6fd6583a
P5.2 through b4fbb034e113a41c26db77cb274f2b3b30f6eee3
P5.3 through 32e836e7789ea72f3ba0d32fe6bdabbb092f5953
P5.4 through 3e2b38d68fe172cd2cf92d7794159f73476ac23d
P5.5 through 8427c8849b1e1f3afa6337de1209a6027410c266
P5.6 through 720102f2a13af5240c779b07cc71ee65994a87b1
P5.7 through 074a71c29a6a6109ae7412e7b1f9850c4449e379
P5.8 through 688f569d441a40a4637ad6a23f111e584e18c955
```

P5 is **COMPLETE**. P5.8 passed its complete repaired-candidate automated and real-environment acceptance chain.

## Current cursor

```text
phase: 6
phase_name: deep task planning, multi-step effects and recent effect journal
phase_state: IN_PROGRESS
active_phase_record: docs/research/AGENTIC_PRODUCT_EVOLUTION_PLAYBOOK.md
active_slice: P6-effect-recovery-journal
active_slice_record: docs/research/P6_EFFECT_RECOVERY_JOURNAL_IMPLEMENTATION.md
active_slice_state: IMPLEMENTED_PENDING_PERIODIC_VALIDATION
current_gate_type: PERIODIC_VALIDATION_DEBT
blocking_work: none
blocking_validation: none for continued implementation
pending_periodic_validation: P6-REAL-MULTISTEP, P6-REAL-LOOP-BOUNDS, P6-REAL-EFFECT-ATOMICITY, P6-REAL-SEGMENTED-RECOVERY, P6-REAL-EFFECT-JOURNAL
periodic_regression_runbook: docs/research/PERIODIC_FULL_REGRESSION_RUNBOOK.md
latest_accepted_evidence: docs/research/evidence/phase5/2026-08-30/P5.8-REAL-ACCEPTANCE-688f569.md
latest_executed_evidence: docs/research/evidence/phase6/2026-08-30/P6-FOCUSED-CHECKPOINT-1d6dc69.md
next_action: implement the coherent P6.2 adaptive/deliberate planning + replan block while keeping accumulated broad/real validation for the next periodic full regression
```

No P6 HARD real gate is recorded PASS yet. Expensive real/browser/full-addon validation is accumulated and executed periodically instead of after every implementation block.

## Phase summary

```text
P0 COMPLETE
P1 COMPLETE
P2 COMPLETE
P3 COMPLETE
P4 COMPLETE
P5 COMPLETE
P6 IN_PROGRESS
  P6.1 TaskPlan vs EffectPlan        IMPLEMENTED_PENDING_PERIODIC_VALIDATION
  P6.2 adaptive/deliberate modes     NOT_STARTED
  P6.3 multi-step EffectPlan         IMPLEMENTED_PENDING_PERIODIC_VALIDATION
  P6.4 atomic vs segmented effects   IMPLEMENTED_PENDING_PERIODIC_VALIDATION
  P6.5 separate budgets              IMPLEMENTED_PENDING_PERIODIC_VALIDATION
  P6.6 EffectJournal                 IMPLEMENTED_PENDING_PERIODIC_VALIDATION
P7+ NOT_ELIGIBLE
```

## Current P6 implementation candidate

### Provider-neutral TaskPlan

Implemented:

```text
fourth neutral NextDecision branch: task_plan_update
closed TaskPlan schema/parser
1..12 bounded user-visible progress steps
strict monotonic revisions: 1 then exactly +1
TaskPlan durable in private working transcript
latest validated TaskPlan projected to approval/final browser response
compact Assistant TaskPlan presentation
TaskPlan contains no capability/args/approval/authority
TaskPlan revisions cannot reset capability failure/terminal-error safety state
```

The TaskPlan is not chain-of-thought and is not executable.

### Bounded EffectPlan

Implemented candidate:

```text
product host opts into max 5 effect steps
legacy/custom callers remain single-step without opt-in
one provider proposal per NextDecision
host accumulates distinct typed proposals
ordered dependency chain
format-v3 prepared steps with step_id + depends_on + recovery metadata
per-step capability/version/args/preview/preconditions/risk/approval/binding
per-step execute + verify under effective user
format-v1/v2 prepared-plan compatibility
post-effect PLAN authority still removed
```

No generic script or provider-side execution authority was added.

### Recovery units

Implemented candidate:

```text
odoo_atomic  -> consecutive Odoo-local steps share one transaction/recovery unit
segmented    -> trusted capability metadata requests a durable internal unit boundary
external     -> intent is durable before non-transactional execution
```

The host preflights a unit before its checkpoint, reacquires the effect lock at every new unit,
rechecks Stop/redirect, persists unit state and commits completed non-final units. An already durable
`executing` unit is never blindly replayed. Internal in-flight units can be distinguished as rolled
back after worker transaction failure; external in-flight units remain uncertain.

### EffectJournal

Implemented candidate:

```text
Odoo-owned odoo.ai.effect.journal
turn/user/company + capability/version binding
recovery unit/mode + classification/state
bounded before/after/receipt evidence
7-day TTL + daily bounded cleanup
system-only direct table access
owned-turn sanitized user projection
reversible / reconstructable / irreversible / external_or_unknown
P5.8 compensation marks reversible journal rows reverted
```

The journal is not a backup and `reconstructable` is not presented as automatic undo.

### Budget families

Implemented foundation:

```text
SafetyBudget
ExplorationBudget
CostBudget
LatencyBudget
ResponseBudget
```

The host enforces effective ceilings. Remaining values are provider context only. Remaining effect capacity is reported rather than the initial maximum.

### Provider boundary

Codex remains the current concrete provider. Core TaskPlan/EffectPlan/recovery/journal/budget/authority logic remains outside Codex. `ADR-021` records the provider-neutral planning/recovery boundary.

## Validation state

The earlier P6.1/P6.3/P6.5 focused deterministic checkpoint passed on `1d6dc695f7fbb26a8d2bef578902d8ce2ebf56b9`. See `docs/research/evidence/phase6/2026-08-30/P6-FOCUSED-CHECKPOINT-1d6dc69.md`.

P6.4/P6.6 implementation and focused tests are now committed, including:

```text
tests/e2e/test_phase6_effect_recovery_contract.py
addons/odoo_ai_assistant/tests/test_effect_journal.py
updated TestCanonicalPlanHostLoop format-v3/recovery assertions
```

Their expensive addon/HOOT/real execution has not been run in this ChatGPT/GitHub environment and is intentionally carried as periodic validation debt. Do not infer PASS from committed tests.

Accumulated real validation debt:

```text
P6-REAL-MULTISTEP
P6-REAL-LOOP-BOUNDS
P6-REAL-EFFECT-ATOMICITY
P6-REAL-SEGMENTED-RECOVERY
P6-REAL-EFFECT-JOURNAL
```

## Remaining coherent Phase-6 work

### P6.2 adaptive/deliberate planning + replan

Still to implement:

```text
adaptive default planning strategy
deliberate/Plan strategy
bounded host-owned mode selection/override
TaskPlan revision behavior when new evidence invalidates an assumption
P6-REAL-REPLAN scenario and tests
```

This is the next coherent implementation block. It remains provider-neutral; provider adapters may receive strategy hints but do not own mode authority or TaskPlan execution semantics.

## Periodic validation policy

Implementation may continue across coherent P6 blocks while broad/real validation debt accumulates. This does not turn unexecuted gates into PASS and does not permit Phase 6 to be called COMPLETE.

The periodic full regression batches:

```text
full current dependency-light/static regression
complete Odoo addon regression
complete @odoo_ai_assistant HOOT suite
permanent high-value real-product smoke scenarios
all applicable named real gates accumulated since the previous accepted full checkpoint
```

If implementation exposes a concrete authority/recovery ambiguity where continuing would make later validation meaningless or unsafe, that specific uncertainty can still become an immediate blocking gate. Ordinary broad regression cost alone is not such a blocker.

## Invariants carried forward

- Odoo remains persistence and operational authority.
- Business operations execute with the effective user and `su=False`.
- `CapabilityDefinition` remains atomic executable authority.
- Provider text/TaskPlan/context never grants execution authority.
- No arbitrary SQL/Python/shell/sudo/unrestricted ORM is exposed.
- P5.5 preview/approval/barrier/verify/post-effect certainty remains authoritative.
- Recovery-unit mode/classification is host-derived, never model authority.
- Persisted in-flight effects are never blindly retried.
- Stop/redirect cannot bypass effect policy or stale-decision checks.
- Raw/private provider reasoning is never browser activity or EffectJournal content.
- Provider-specific adapters stay below the neutral agent contract.
- No GitHub Actions are used while repository policy says runners are unavailable.
- Roadmap blocks are the largest coherent feasible product change; commit count does not define slice count.

## Exact stop rule

Do not call any P6 subpart accepted or Phase 6 COMPLETE until its applicable periodic real/full regression evidence is green. Continued implementation of P6.2 is allowed while the explicit validation debt above remains pending, unless a new concrete authority/recovery uncertainty is discovered that makes further design unsafe.
