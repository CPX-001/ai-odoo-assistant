# Stabilization execution state

State format: 36
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
active_slice: P6-planning-bounded-effectplan-budgets
active_slice_record: docs/research/P6_PLANNING_EFFECTPLAN_IMPLEMENTATION.md
active_slice_state: REAL_ENV_VALIDATION_REQUIRED
current_gate_type: HARD
blocking_work: none
blocking_validation: P6-REAL-MULTISTEP, P6-REAL-LOOP-BOUNDS
latest_accepted_evidence: docs/research/evidence/phase5/2026-08-30/P5.8-REAL-ACCEPTANCE-688f569.md
latest_executed_evidence: docs/research/evidence/phase6/2026-08-30/P6-FOCUSED-CHECKPOINT-1d6dc69.md
next_action: execute P6-REAL-MULTISTEP and P6-REAL-LOOP-BOUNDS on the materially unchanged candidate before P6.4/P6.6
```

No P6 HARD real gate is recorded PASS yet.

## Phase summary

```text
P0 COMPLETE
P1 COMPLETE
P2 COMPLETE
P3 COMPLETE
P4 COMPLETE
P5 COMPLETE
P6 IN_PROGRESS
  P6.1 TaskPlan vs EffectPlan        REAL_ENV_VALIDATION_REQUIRED
  P6.2 adaptive/deliberate modes     NOT_STARTED
  P6.3 multi-step EffectPlan         REAL_ENV_VALIDATION_REQUIRED
  P6.4 atomic vs segmented effects   NOT_STARTED
  P6.5 separate budgets              REAL_ENV_VALIDATION_REQUIRED
  P6.6 EffectJournal                 NOT_STARTED
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
format-v2 prepared steps with step_id + depends_on
per-step capability/version/args/preview/preconditions/risk/approval/binding
one durable barrier for the current Odoo-local recovery unit
per-step execute + verify under effective user
format-v1 prepared-plan compatibility
post-effect PLAN authority still removed
```

No generic script or provider-side execution authority was added.

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

Codex remains the current concrete provider. `codex_decision.py` now translates the four-way neutral decision schema and instructs Codex to:

```text
use TaskPlan only as non-authoritative visible progress
propose distinct effect steps one at a time
never duplicate already staged plan_step_proposed items
never claim execution before verified_effect_receipt
```

Core TaskPlan/EffectPlan/budget/authority logic remains outside Codex.

## Deterministic checkpoint result

The focused deterministic checkpoint passed on `1d6dc695f7fbb26a8d2bef578902d8ce2ebf56b9`. See `docs/research/evidence/phase6/2026-08-30/P6-FOCUSED-CHECKPOINT-1d6dc69.md`.

Executed as one focused checkpoint:

```text
1. dependency-light Phase-6 + NextDecision + canonical EffectPlan tests
2. focused Odoo addon tests:
   - TestCanonicalPlanHostLoop
   - TestCodexDecisionAdapter
   - TestPostEffectReasoning
   - relevant capability action/revalidation/compensation tests
3. directly affected addon tests not already covered by the focused classes
4. focused browser/HOOT/static validation for the TaskPlan template and its touched P5 live/approval integration points
```

This checkpoint does not require a full addon, HOOT/browser or repository regression. Broad regression runs require an explicit user request or a later authoritative gate that names the full suite.

The remaining real gates attributable to this checkpoint are:

```text
P6-REAL-MULTISTEP
P6-REAL-LOOP-BOUNDS
```

Do not mark these PASS from code inspection.

## Work deliberately deferred

### P6.2

Adaptive/deliberate/auto planning strategy, measured complexity selection, richer replan UX and a dedicated live TaskPlan projection.

### P6.4

Explicit recovery units for:

```text
Odoo-local atomic groups
segmented durable groups
future external/non-transactional effects
```

Do not imply atomic rollback for future external effects.

### P6.6

Short-TTL Odoo-owned EffectJournal with operation classification and bounded before/after/receipt evidence.

Existing P5.8 compensation remains reusable but is not the EffectJournal.

## Invariants carried forward

- Odoo remains persistence and operational authority.
- Business operations execute with the effective user and `su=False`.
- `CapabilityDefinition` remains atomic executable authority.
- Provider text/TaskPlan/context never grants execution authority.
- No arbitrary SQL/Python/shell/sudo/unrestricted ORM is exposed.
- P5.5 preview/approval/barrier/verify/post-effect certainty remains authoritative.
- Stop/redirect cannot bypass effect policy or stale-decision checks.
- Raw/private provider reasoning is never browser activity.
- Provider-specific adapters stay below the neutral agent contract.
- No GitHub Actions are used while repository policy says runners are unavailable.
- Roadmap slices are the largest coherent feasible product change; commit count does not define slice count.

## Exact stop rule

Do not begin P6.4 segmented recovery or P6.6 EffectJournal until `P6-REAL-MULTISTEP` and `P6-REAL-LOOP-BOUNDS` are reviewed green. A failed HARD gate creates repair work inside this same coherent slice.
