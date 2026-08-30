# Unified agent runtime

The active product runtime is a single Odoo-owned, host-authorized agent loop embedded in the `odoo_ai_assistant` addon. It supersedes both the retired rigid workflow router and the old provider-owned monolithic tool loop.

Current code plus accepted ADRs are authoritative. Product direction is in `PRODUCT_VISION.md`; exact roadmap/validation state is in `research/EXECUTION_STATE.md`.

## Active turn shape

```text
browser
 -> Odoo durable turn
 -> bounded cron lease under originating user (su=False)
 -> effective CapabilityRegistry + immutable turn settings/context snapshot
 -> private bounded working transcript
 -> provider-neutral NextDecisionEngine returns exactly one NextDecision
      task_plan_update
      reasoning_capability_call
      plan_step_proposal
      final_answer
 -> Odoo validates the decision
 -> repeat until final/staged effects
```

The host — not the provider — owns capabilities, budgets, policy, approval, business execution, verification and recovery certainty.

`CapabilityDefinition` remains the atomic executable authority contract. A provider never gains an Odoo Environment and cannot create authority by naming an arbitrary ORM method, SQL, Python, shell or sudo operation.

## Provider-neutral decision port

The current neutral `NextDecision` union has four branches:

```text
final_answer
  final user-facing answer

task_plan_update
  non-authoritative visible TaskPlan revision

reasoning_capability_call
  request one currently revealed REASONING capability

plan_step_proposal
  stage one currently revealed PLAN capability as a proposed effect
```

Codex App Server is the current concrete provider. Its adapter translates this neutral contract to the App Server Structured Outputs wire format, normalizes provider errors and handles Codex-specific steer/interrupt/model options. It does not own the agent loop.

A future provider should implement the same `NextDecisionEngine` port rather than copy Odoo orchestration.

## TaskPlan

Phase 6 introduces a separate user-visible TaskPlan:

```text
goal
revision
steps:
  step_id
  title
  state
  depends_on
```

It is explicitly **not** executable authority:

- no capability name;
- no capability arguments;
- no approval decision;
- no script or arbitrary program;
- no private chain-of-thought.

The host reparses each revision, requires revision `1` then exact `+1`, persists it in the private working transcript and exposes only the latest validated payload to the browser response.

TaskPlan updates cannot erase terminal policy/authority errors or reset a failing capability streak.

## Reasoning capabilities

For each `reasoning_capability_call` the host:

1. resolves the name from the effective REASONING catalog;
2. validates the arguments against the current definition/schema;
3. enforces call/budget limits;
4. executes through `CapabilityExecutor` with `ExecutionAuthority.REASONING` under the effective Odoo user;
5. records a bounded result or safe error;
6. asks the provider for the next decision.

Hidden/disabled capabilities cannot be called by guessing their names.

## Bounded EffectPlan

A `plan_step_proposal` remains stage-only. Phase 6 now lets the product host accumulate up to **5** distinct typed proposals before preparation. Legacy/custom callers remain single-step unless they receive the Phase-6 policy opt-in.

The current host derives a deterministic ordered dependency chain and sends the resulting tuple to `CapabilityPlanService.prepare()`.

Prepared EffectPlan v2 steps preserve:

```text
step_id / depends_on
capability + version
validated arguments
preview
risk / effect / approval
precondition fingerprint
binding fingerprint
semantic correlation groups
result / verification
```

There is no generic script body.

## Current Odoo-local effect lifecycle

For the currently supported Odoo-local effect capabilities:

```text
propose distinct typed steps
 -> host accumulates and validates
 -> preview all steps
 -> policy / approval
 -> revalidate step capability/version/binding/precondition
 -> one durable write barrier for the Odoo-local recovery unit
 -> execute + verify each step in order under effective user
 -> persist completed plan + verified-effect receipt
 -> remove PLAN authority
 -> optional REASONING-only post-effect continuation
 -> natural final answer
```

The business effects currently share the normal Odoo transaction. A failure before commit rolls that Odoo-local transaction back normally.

This does **not** imply that future external/non-transactional effects will be atomic. P6.4 must model segmented recovery units explicitly before those effects can participate safely.

Existing explicit P5.8 HOST-only compensators can reverse eligible completed internal effects in reverse order when their optimistic preconditions still match. They are not a database-wide rollback and are not the future EffectJournal.

## Working transcript and restartability

The private working transcript stores bounded typed continuation state such as:

```text
user input
TaskPlan revisions
provider decisions
capability calls/results/errors
staged EffectPlan steps
prepared plan checkpoint
verified-effect receipt
final answer
```

It is not conversation history and not chain-of-thought.

On restart, pending calls are closed as interrupted rather than blindly replayed. Provider process/thread persistence is never business durability.

## Separate budgets

The host resolves separate families:

```text
SafetyBudget
ExplorationBudget
CostBudget
LatencyBudget
ResponseBudget
```

Current Cost/Latency families begin with enforceable provider-decision ceilings; later provider telemetry can refine them without moving authority out of Odoo.

The effective provider-decision limit is host-derived. Remaining counters sent to a provider are advisory context only.

## Public/live projections

Private working state and browser-visible state remain deliberately separate.

Current user-facing channels include:

- sanitized host-owned semantic activity;
- optional bounded readable reasoning summaries that never expose raw private reasoning;
- provisional answer deltas;
- final validated response;
- latest validated TaskPlan on approval/final responses;
- typed navigation references revalidated by Odoo before navigation.

Phase 6 has not yet added a dedicated running-turn live TaskPlan stream; that belongs with P6.2 deliberate/adaptive UX rather than weakening the closed P5.8 public-activity contract.

## Turn control and concurrency

Accepted Phase-5 behavior remains:

- one active causal turn per conversation;
- multiple conversations can run concurrently within bounded scheduler capacity;
- per-conversation frontend state;
- durable reconnect/replay;
- immutable settings/context snapshots for in-flight turns;
- same-turn correction/redirect and Stop;
- stale control decisions rejected before the effect barrier;
- approval superseded safely by a newer correction.

## Failure semantics

Provider/runtime failures are normalized into bounded machine facts and product state. Raw provider messages are not the public failure contract.

After an effect outcome becomes ambiguous, the host never converts a provider error into a blind “safe to retry” signal. Verified receipt / recovery state remains authoritative.

## Current validation status

P0-P5 are accepted complete. P5.8 acceptance evidence is recorded under:

```text
research/evidence/phase5/2026-08-30/P5.8-REAL-ACCEPTANCE-688f569.md
```

P6 is in progress. The combined P6.1/P6.3/P6.5 implementation candidate exists on `main`, but its final deterministic/real validation is still pending. No P6 HARD gate is currently recorded PASS.

See `research/P6_PLANNING_EFFECTPLAN_IMPLEMENTATION.md` and `research/EXECUTION_STATE.md` for the exact boundary.
