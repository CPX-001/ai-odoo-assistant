# Stabilization execution state

State format: 41
Updated: 2026-08-31

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

P5 is **COMPLETE** and remains the latest fully accepted phase.

## Current cursor

```text
phase: 6
phase_name: deep task planning, multi-step effects and recent effect journal
phase_state: IMPLEMENTED_PENDING_PERIODIC_VALIDATION
active_phase_record: docs/research/AGENTIC_PRODUCT_EVOLUTION_PLAYBOOK.md
active_slice: P6-final-implementation-candidate
active_slice_record: docs/research/P6_ADAPTIVE_PLANNING_IMPLEMENTATION.md
active_slice_state: IMPLEMENTED_PENDING_PERIODIC_VALIDATION
current_gate_type: FOCUSED_IMPLEMENTATION_FOLLOWUP
blocking_work: short-turn latency remains above the near-immediate product target (14.75s direct capability answer; 30.55s bounded quotation count)
blocking_validation: Phase 6 periodic regression and named real-product gates remain unexecuted against the new candidate; Phase 7 remains ineligible
pending_periodic_validation: P6-REAL-MULTISTEP, P6-REAL-REPLAN, P6-REAL-EFFECT-ATOMICITY, P6-REAL-SEGMENTED-RECOVERY, P6-REAL-LOOP-BOUNDS, P6-REAL-EFFECT-JOURNAL
periodic_regression_runbook: docs/research/PERIODIC_FULL_REGRESSION_RUNBOOK.md
latest_accepted_evidence: docs/research/evidence/phase5/2026-08-30/P5.8-REAL-ACCEPTANCE-688f569.md
latest_executed_evidence: docs/research/evidence/phase6/2026-08-31/SEMANTIC-ROUTING-9197be6.md
periodic_stage_status: historical A-C PASS on 46b1093; D was BLOCKED there; provider access is now restored but the periodic batch has not run against 9197be6
next_action: reduce repeated provider latency for short direct/read turns without weakening the host-owned NextDecision/capability boundary, then run the applicable periodic validation against one final candidate
```

No unexecuted P6 HARD gate is PASS. Stages A-C remain historical green evidence for product
candidate `46b1093`, not for the newer candidate. Provider access has recovered and the focused
semantic smoke on `9197be6` completed, but it was not the periodic Stage-D/P6 acceptance batch.

## Phase summary

```text
P0 COMPLETE
P1 COMPLETE
P2 COMPLETE
P3 COMPLETE
P4 COMPLETE
P5 COMPLETE
P6 IMPLEMENTED_PENDING_PERIODIC_VALIDATION
  P6.1 TaskPlan vs EffectPlan        IMPLEMENTED_PENDING_PERIODIC_VALIDATION
  P6.2 adaptive/deliberate/replan    IMPLEMENTED_PENDING_PERIODIC_VALIDATION
  P6.3 multi-step EffectPlan         IMPLEMENTED_PENDING_PERIODIC_VALIDATION
  P6.4 atomic vs segmented effects   IMPLEMENTED_PENDING_PERIODIC_VALIDATION
  P6.5 separate budgets              IMPLEMENTED_PENDING_PERIODIC_VALIDATION
  P6.6 EffectJournal                 IMPLEMENTED_PENDING_PERIODIC_VALIDATION
P7+ NOT_ELIGIBLE
```

## Current Phase-6 implementation candidate

The current implementation candidate is `9197be6659f7397ed577ec41d813764dcd5ca998`.
It adds semantic short-turn routing, host-owned TaskPlan transition schema, adaptive suppression of
artificial plans, lazy public work activity and terminal failure collapse. Focused evidence is:

```text
docs/research/evidence/phase6/2026-08-31/SEMANTIC-ROUTING-9197be6.md
```

Correctness is green for the focused contract and real smoke. Performance is not accepted: the
measured short-turn latencies remain explicit implementation debt.

### P6.1 / P6.2 — visible planning without authority

Implemented:

```text
provider-neutral task_plan_update NextDecision branch
TaskPlan 1..12 bounded public steps
planning modes: adaptive | deliberate | auto
planning mode captured immutably per turn
host-derived auto complexity score from structural request/screen signals only
PlanningDecisionEngine above provider adapters
deliberate mode requires initial TaskPlan before capability/effect requests
TaskPlan revision_kind: initial | progress | replan
progress cannot mutate plan structure
structural replan requires new host-observed evidence
replan carries short public revision_summary
live running-turn TaskPlan projection without capability args/private reasoning
```

Planning mode is not autonomy and cannot change ACL, capability availability, approval or execution authority.

### P6.3 — bounded EffectPlan

Implemented:

```text
max 5 typed effect steps
host accumulation and dependency ordering
format-v3 prepared plan
per-step version/arguments/preview/preconditions/risk/approval/binding
format-v1/v2 execution compatibility
post-effect PLAN authority removed
```

### P6.4 — recovery units

Implemented:

```text
odoo_atomic
segmented
external
```

Recovery mode is trusted host/capability metadata, not provider authority. Units are preflighted, durably checkpointed where required, Stop/redirect is rechecked at each new boundary, and a persisted in-flight unit is not blindly replayed.

### P6.5 — separate budget families

Implemented foundation:

```text
SafetyBudget
ExplorationBudget
CostBudget
LatencyBudget
ResponseBudget
```

Remaining counters are provider context only; host enforcement remains authoritative.

### P6.6 — EffectJournal

Implemented:

```text
Odoo-owned recent effect journal
bounded before/after/receipt evidence
recovery unit/state binding
7-day TTL + bounded cron cleanup
system-only raw records + owned-turn sanitized projection
reversible / reconstructable / irreversible / external_or_unknown
verified P5.8 compensation marks matching rows reverted
```

The journal is not a backup and does not turn reconstructable effects into automatic undo.

## Provider boundary

Codex is still the concrete configured provider, but it does not own the Phase-6 logic. The neutral path is:

```text
Odoo host
 -> PlanningDecisionEngine
 -> NextDecisionEngine provider port
 -> Codex adapter today / other adapters later
```

TaskPlan, EffectPlan, budgets, ACL/policy, approval, recovery units, EffectJournal, execution and verification stay above provider adapters.

## Validation state

Recorded focused checkpoint already green for the earlier P6.1/P6.3/P6.5 foundation:

```text
docs/research/evidence/phase6/2026-08-30/P6-FOCUSED-CHECKPOINT-1d6dc69.md
```

The periodic regression on product candidate `46b1093` executed and passed the complete current
dependency-light/static stage, complete Odoo addon stage and complete addon HOOT stage. Its
consolidated evidence is:

```text
docs/research/evidence/regression/2026-08-30/FULL-REGRESSION-46b1093.md
```

The earlier real-product stage on `46b1093` returned `usageLimitExceeded` before the first provider
decision. Provider access is available again, and `9197be6` has focused real semantic-routing
evidence, but the named Phase-6 real gates have not been rerun and remain pending rather than PASS.

Accumulated periodic real debt:

```text
P6-REAL-MULTISTEP
P6-REAL-REPLAN
P6-REAL-EFFECT-ATOMICITY
P6-REAL-SEGMENTED-RECOVERY
P6-REAL-LOOP-BOUNDS
P6-REAL-EFFECT-JOURNAL
```

Restore provider capacity and resume Stage D according to
`PERIODIC_FULL_REGRESSION_RUNBOOK.md`, without rerunning already-green A-C unless the product
candidate changes or a Stage-D repair affects them.

## Invariants carried forward

- Odoo remains persistence and operational authority.
- Business operations execute under the effective user with `su=False`.
- `CapabilityDefinition` remains atomic executable authority.
- Planning strategy and TaskPlan never grant effect authority.
- No arbitrary SQL/Python/shell/sudo/unrestricted ORM is exposed.
- Policy/approval/preconditions/write-barrier/verification remain host-owned.
- Recovery-unit mode/classification is host-derived.
- Persisted in-flight effects are never blindly retried.
- Stop/redirect cannot bypass the effect boundary.
- Raw/private provider reasoning never becomes TaskPlan/activity/journal content.
- Provider-specific adapters remain below the neutral decision contract.
- Broad/real validation is batched periodically rather than repeated after every implementation slice.
- No GitHub Actions are used while repository policy says usable runners are unavailable.

## Exact stop rule

Do not begin Phase 7 and do not call Phase 6 COMPLETE until the applicable periodic full regression and named Phase-6 real gates are green against the same final candidate lineage. If that batch fails, repair the concrete underlying contract with focused tests, then rerun only the affected broad stage before the final acceptance rerun as defined by the periodic runbook.
