# Stabilization execution state

State format: 43
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
phase_state: PART1_VALIDATED_PHASE2_PENDING
active_phase_record: docs/research/AGENTIC_PRODUCT_EVOLUTION_PLAYBOOK.md
active_slice: P6-validation-part2-pending
active_slice_record: docs/research/P6_PLANNING_EFFECTPLAN_IMPLEMENTATION.md
active_slice_state: PHASE1_VALIDATED_STOPPED_BEFORE_PHASE2
current_gate_type: PHASE2_REAL_VALIDATION
blocking_work: none for P6.1/P6.2/P6.3/P6.5; Phase 2 was explicitly outside the 2026-08-31 validation run
blocking_validation: P6.4/P6.6 real recovery/journal gates and the applicable final periodic regression remain unexecuted; Phase 6 is not COMPLETE and Phase 7 remains ineligible
pending_periodic_validation: P6-REAL-EFFECT-ATOMICITY, P6-REAL-SEGMENTED-RECOVERY, P6-REAL-EFFECT-JOURNAL, applicable final periodic regression
periodic_regression_runbook: docs/research/PERIODIC_FULL_REGRESSION_RUNBOOK.md
latest_accepted_evidence: docs/research/evidence/phase5/2026-08-30/P5.8-REAL-ACCEPTANCE-688f569.md
latest_executed_evidence: docs/research/evidence/phase6/2026-08-31/P6-VALIDATION-PART1-2689691.md
periodic_stage_status: historical A-C PASS on 46b1093; D was BLOCKED there; no periodic batch has run against the current Direct/Plan candidate
next_action: in a separate Phase-2 run, execute only P6-REAL-EFFECT-ATOMICITY, P6-REAL-SEGMENTED-RECOVERY and P6-REAL-EFFECT-JOURNAL; do not infer those results from Part 1
```

Part-1 evidence at `2689691` validates P6.1/P6.2/P6.3/P6.5 and the real multistep, replan and loop-bound gates. No unexecuted Phase-2 gate is PASS.

## Phase summary

```text
P0 COMPLETE
P1 COMPLETE
P2 COMPLETE
P3 COMPLETE
P4 COMPLETE
P5 COMPLETE
P6 PART1_VALIDATED_PHASE2_PENDING
  P6.1 TaskPlan vs EffectPlan        VALIDATED_PART1
  P6.2 direct/deliberate/replan      VALIDATED_PART1
  P6.3 multi-step EffectPlan         VALIDATED_PART1
  P6.4 atomic vs segmented effects   IMPLEMENTED_PENDING_PERIODIC_VALIDATION
  P6.5 separate budgets              VALIDATED_PART1
  P6.6 EffectJournal                 IMPLEMENTED_PENDING_PERIODIC_VALIDATION
P7+ NOT_ELIGIBLE
```

## Current Phase-6 implementation candidate

The current product candidate through `3103f7028f0f346c5a6789da9618bb5876f9b91d` changes the
planning boundary after the earlier `9197be6` semantic-routing checkpoint.

Current behavior:

```text
Directo / adaptive is the default
new Direct turns cannot create a TaskPlan
Direct may perform multiple bounded reads and stage short EffectPlans
number of tool/effect calls never promotes Direct into visible planning
Plan / deliberate is explicit user opt-in
Plan requires an initial TaskPlan before capability/effect work
former Auto is removed from the product surface and rejected for new preferences
legacy stored Auto normalizes to Direct for new turns
historical immutable Auto snapshots remain readable
structural complexity remains diagnostic/eval evidence only
lazy public work activity remains intact
```

The addon version is `18.0.13.3.0` for this product behavior follow-up.

The change deliberately does **not** claim that short-turn latency is solved. It removes artificial
planning overhead, while the current one-decision-at-a-time Codex path can still spend multiple
provider generations on schema/read/effect chains.

### P6.1 / P6.2 — visible planning without authority

Implemented:

```text
provider-neutral task_plan_update NextDecision branch
TaskPlan 1..12 bounded public steps
user-facing planning modes: Directo | Plan
stable stored identities: adaptive | deliberate
legacy auto read compatibility only
planning mode captured immutably per turn
host-derived structural complexity score retained as diagnostic evidence
PlanningDecisionEngine above provider adapters
Direct new-turn task_plan_available=false
Deliberate requires initial TaskPlan before capability/effect requests
TaskPlan revision_kind: initial | progress | replan
progress cannot mutate plan structure
structural replan requires new host-observed evidence
replan carries short public revision_summary
live running-turn TaskPlan projection without capability args/private reasoning
```

Planning mode is not autonomy and cannot change ACL, capability availability, approval or execution authority.

Prepared focused contracts now explicitly cover a normal short action chain remaining planless:

```text
look up Demo
 -> stage/create Demo if needed
 -> stage/create a test quotation
```

That is an EffectPlan/orchestration concern, not a reason to expose a TaskPlan.

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

The Direct/Plan repair is host-enforced. `PlanningDecisionEngine` projects
`task_plan_available=false` for a new Direct turn and the Codex Structured Outputs adapter removes
the `task_plan_update` branch from the wire schema. The model therefore cannot create a visible plan
merely because a prompt is long or because two capability results already exist.

## Performance follow-up

The previous focused real smoke measured:

```text
capability explanation     14.75s
bounded quotation count    30.55s
```

Those values are baseline evidence from `9197be6`, not measurements of the current candidate.

Historical provider timing also shows that App Server initialization/thread creation has measurable
cost, but provider/model generation is a larger contributor on a simple greeting. The next
performance slice should therefore be evidence-driven rather than another intent-router patch.

Preferred investigation order:

```text
1. measure provider decisions + process/thread/model timing on the focused semantic matrix
2. reuse initialized App Server state within one durable Odoo turn if it materially helps
3. reduce schema/query technical round-trips through safe host-owned capability composition or an equivalent continuation seam
4. evaluate model/reasoning-effort fast routing only with explicit product semantics and agent evals
```

Do not reintroduce rigid GENERAL/QUERY/HOW_TO/ACTION routing and do not make TaskPlan automatic to solve latency.

## Validation state

Phase-6 Part-1 focused validation is recorded at:

```text
docs/research/evidence/phase6/2026-08-31/P6-VALIDATION-PART1-2689691.md
```

Against product/test candidate `268969184c7fbeff479d3f22308576c526ba2692`, the focused
dependency-light, Odoo and HOOT checks passed, as did P6-REAL-MULTISTEP, P6-REAL-REPLAN and
P6-REAL-LOOP-BOUNDS. The real replan gate found and repaired a bounded-convergence defect: after a
rejected no-op progress revision, the host now temporarily removes the TaskPlan decision branch so
the next provider decision must advance the turn. TaskPlan revisions cannot reset provider or
correctable/consecutive failure counters.

This checkpoint does not validate P6.4/P6.6. The exact remaining Phase-2 gates are:

```text
P6-REAL-EFFECT-ATOMICITY
P6-REAL-SEGMENTED-RECOVERY
P6-REAL-EFFECT-JOURNAL
```

Recorded focused checkpoint already green for the earlier P6.1/P6.3/P6.5 foundation:

```text
docs/research/evidence/phase6/2026-08-30/P6-FOCUSED-CHECKPOINT-1d6dc69.md
```

The earlier semantic-routing checkpoint is:

```text
docs/research/evidence/phase6/2026-08-31/SEMANTIC-ROUTING-9197be6.md
```

It remains useful baseline evidence but predates the explicit Direct/Plan follow-up.

Prepared but not yet executed focused coverage for the follow-up includes:

```text
tests/e2e/test_phase6_adaptive_planning_contract.py
tests/e2e/test_phase6_direct_mode_short_chain_contract.py
addons/odoo_ai_assistant/tests/test_planning_preferences.py
addons/odoo_ai_assistant/tests/test_turn_settings_snapshot.py
addons/odoo_ai_assistant/static/tests/assistant_planning_service.test.js
```

The periodic regression on product candidate `46b1093` previously passed the complete dependency-light/static stage, complete Odoo addon stage and complete addon HOOT stage. Its consolidated evidence is:

```text
docs/research/evidence/regression/2026-08-30/FULL-REGRESSION-46b1093.md
```

That evidence is historical and does not validate this newer candidate.

Remaining real Phase-2 debt is:

```text
P6-REAL-EFFECT-ATOMICITY
P6-REAL-SEGMENTED-RECOVERY
P6-REAL-EFFECT-JOURNAL
```

## Invariants carried forward

- Odoo remains persistence and operational authority.
- Business operations execute under the effective user with `su=False`.
- `CapabilityDefinition` remains atomic executable authority.
- Planning strategy and TaskPlan never grant effect authority.
- Direct mode does not weaken EffectPlan/policy/approval/verification.
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

Do not begin Phase 7 and do not call Phase 6 COMPLETE until the applicable periodic full regression and named Phase-6 real gates are green against the same final candidate lineage. Before that final batch, the current Direct/Plan follow-up needs its focused deterministic/Odoo/HOOT/real semantic smoke. If the focused smoke exposes latency without a correctness failure, address the measured provider round-trip bottleneck as a performance follow-up rather than weakening the planning/authority contract.
