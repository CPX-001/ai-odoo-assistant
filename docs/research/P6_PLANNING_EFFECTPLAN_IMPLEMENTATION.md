# Phase 6 planning / bounded EffectPlan implementation

Date: 2026-08-30  
Status: **FOCUSED DETERMINISTIC CHECKPOINT GREEN — REAL VALIDATION REQUIRED**
Scope: P6.1 + P6.3 + P6.5 foundation, with the smallest useful TaskPlan presentation layer  
Prerequisite: accepted P5.8 lineage through `688f569d441a40a4637ad6a23f111e584e18c955`

This record describes the current Phase-6 checkpoint. It does **not** mark any P6 real gate as passed.

## 1. Problem

P5 deliberately limited effectful turns to one canonical step. That was useful while stabilizing the host loop, approval, write barrier, verification and post-effect certainty, but it prevents ordinary requests such as “update these two records” from becoming one coherent safe plan.

At the same time, a modern agent needs a user-visible plan for longer investigation/resolution work without turning that plan into executable authority.

Phase 6 therefore separates two concepts:

```text
TaskPlan
  user-visible progress / resolution structure
  mutable only by explicit revisions
  no capability names/arguments/approval/execution authority

EffectPlan
  bounded typed proposed effects
  every step remains a CapabilityDefinition invocation
  host validates/previews/policies/approves/revalidates/executes/verifies
```

## 2. Provider-neutral boundary

The host loop remains provider-neutral. `NextDecisionEngine` now returns one of:

```text
final_answer
 task_plan_update
 reasoning_capability_call
 plan_step_proposal
```

`task_plan_update` is a closed provider-neutral contract. The host reparses it, requires monotonic revisions (`1`, then exactly `+1`), persists it in the private working transcript and exposes only the validated latest revision to the browser response.

The TaskPlan schema intentionally has no fields for:

```text
capability
arguments
approval
authority
script / SQL / Python / shell
```

A TaskPlan revision also cannot clear a terminal capability/policy error or reset a failing-tool streak; otherwise harmless plan updates could be used to evade safety budgets.

Codex remains the concrete provider currently wired into the product. `codex_decision.py` translates the neutral four-way contract to the App Server Structured Outputs shape and supplies Codex-specific instructions. Future providers should implement the same neutral `NextDecisionEngine` rather than duplicate the Odoo agent loop.

## 3. TaskPlan behavior in this checkpoint

A TaskPlan contains:

```text
goal
revision
1..12 steps
  step_id
  title
  state: pending | in_progress | completed | blocked | skipped
  depends_on: earlier TaskPlan step ids only
```

It is stored as a typed `task_plan` working item. It is not chain-of-thought and does not contain hidden reasoning.

The latest validated TaskPlan is included in terminal/approval browser responses and rendered as a compact “Plan de trabajo” panel. The UI explicitly explains that Odoo actions are validated and authorized separately.

This checkpoint does **not** claim the richer P6.2 deliberate/auto strategy or a dedicated live TaskPlan event stream. Running-turn live TaskPlan projection can be added with that product-mode work rather than weakening the already closed P5.8 public-activity contract.

## 4. Bounded multi-step EffectPlan

The product host opts into up to **5** effect steps per plan. Legacy/custom callers that do not receive the new normalized policy remain single-step for compatibility.

The provider still proposes only one effect step per decision. The host accumulates distinct `plan_step_proposal` working items and turns them into ordered `PlannedCapability` values. Current dependency semantics are deliberately simple and deterministic: each later provider-proposed effect depends on the preceding effect.

`CapabilityPlanService.prepare()` produces format v2 steps containing at least:

```text
position
step_id
depends_on
capability + version
validated arguments
title
risk / effect / approval
approval_required
precondition_fingerprint
binding_fingerprint
preview
semantic groups
state/result/verification
```

At execution time the host re-resolves every capability, checks version/binding/preconditions/approval again, enforces dependency completion, executes with `ExecutionAuthority.PLAN`, and verifies every step.

There is still no generic program/script body.

## 5. Current atomicity boundary

For the currently supported Odoo-local effect capabilities, the plan executes in order inside one Odoo business transaction after one durable pre-effect barrier.

Conceptually:

```text
prepare all typed steps
 -> approval/policy
 -> revalidate step 1
 -> one durable write barrier
 -> execute + verify step 1
 -> revalidate/execute + verify step 2
 -> ...
 -> commit/rollback through the normal Odoo transaction boundary
```

This checkpoint does **not** claim atomicity for future external or non-transactional effects. P6.4 must explicitly introduce recovery units/segmentation before such effects can be described as safe multi-step execution.

Existing P5.8 host-only compensators already operate over completed plans in reverse step order and remain reusable infrastructure. They do not substitute for P6.4 segmented recovery.

## 6. Separate budget families

The host now resolves distinct bounded families:

```text
SafetyBudget
  max_effect_steps
  max_consecutive_failures

ExplorationBudget
  max_provider_decisions
  max_capability_calls

CostBudget
  max_provider_decisions (current first enforceable cost proxy)

LatencyBudget
  max_provider_decisions (current first enforceable latency proxy)

ResponseBudget
  max_transcript_bytes
  max_result_bytes
```

The effective provider-decision ceiling is the minimum of exploration/cost/latency ceilings. Remaining counters are sent to the provider only as context; they never become provider authority.

`remaining_budgets.effect_steps` reports remaining effect capacity, not the original maximum.

This is the P6.5 foundation. Future provider-native token/cost/time telemetry may refine Cost/Latency budgets without moving authority out of the host.

## 7. Codex-specific implementation kept narrow

Codex-specific code owns only transport/provider behavior such as:

```text
App Server process/thread/turn lifecycle
Structured Outputs wire translation
Codex model/reasoning options
provider notifications/errors/backpressure
turn/steer and turn/interrupt
Codex instructions explaining the neutral contract
```

It does not own:

```text
TaskPlan revision authority
EffectPlan accumulation or execution
capability schema validation
ACL/policy/approval
write barrier
verification
budgets
recovery semantics
```

This is the intended seam for adding another provider later.

## 8. Compatibility and non-goals

Preserved:

- effective-user `su=False` business access;
- `CapabilityDefinition` as atomic executable authority;
- provider-side tools disabled for the decision adapter;
- P5.5 barrier/verification/post-effect certainty;
- P5.8 stop/redirect and compensation boundaries;
- format-v1 prepared plan compatibility;
- single-step behavior for callers that do not explicitly opt into P6 multi-step limits.

Not implemented/claimed by this checkpoint:

- P6.2 adaptive/deliberate/auto planning strategy;
- evidence-driven replan semantics beyond ordinary repeated host decisions;
- P6.4 segmented/external recovery units;
- P6.6 EffectJournal;
- any P6 HARD real gate PASS.

## 9. Deterministic coverage added/updated

Coverage now includes contracts for:

- TaskPlan parsing, dependencies and forbidden authority fields;
- TaskPlan as the fourth provider-neutral `NextDecision` branch;
- exact TaskPlan revision increments;
- TaskPlan + two staged Odoo effects remaining separate;
- legacy single-step compatibility;
- product multi-step opt-in;
- independent budget families and remaining effect-step accounting;
- maximum five-effect ceiling;
- two ordered Odoo patches in one EffectPlan;
- one barrier for the Odoo-local plan and per-step verification;
- Codex Structured Outputs four-way decision translation;
- Codex instructions that forbid duplicate effect proposals and false execution claims.

The focused deterministic checkpoint passed on `1d6dc695f7fbb26a8d2bef578902d8ce2ebf56b9`. Evidence: `evidence/phase6/2026-08-30/P6-FOCUSED-CHECKPOINT-1d6dc69.md`.

## 10. Validation boundary / next work

The meaningful focused checkpoint below is green. P6.4/P6.6 remain blocked by the two named real gates, not by a full regression suite.

Minimum candidate validation should include:

```text
dependency-light Phase-6/agent contract tests
focused Odoo tests:
  test_canonical_plan_host_loop
  test_codex_decision_adapter
  test_post_effect_reasoning
  relevant capability action/revalidation/compensation tests
then only directly affected addon/browser tests not already covered above
```

This checkpoint does not require a full addon, HOOT/browser or repository regression. Under the repository test-scope rule, those broad suites run only if the user explicitly requests them or a later authoritative gate names them explicitly.

After deterministic validation is green, run the real gates that this checkpoint can honestly exercise:

```text
P6-REAL-MULTISTEP
P6-REAL-LOOP-BOUNDS
```

`P6-REAL-REPLAN`, `P6-REAL-EFFECT-ATOMICITY`, `P6-REAL-SEGMENTED-RECOVERY` and `P6-REAL-EFFECT-JOURNAL` remain tied to later P6 work unless the gate definition is explicitly narrowed by a newer accepted record.
