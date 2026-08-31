# Phase 6.2 direct/deliberate planning implementation

Date: 2026-08-31  
Status: **IMPLEMENTED CANDIDATE — PERIODIC VALIDATION REQUIRED**

This record describes the current Phase-6 planning behavior. It does not claim any unexecuted HARD gate as PASS.

## 1. Problem

`TaskPlan` is useful as visible progress for genuinely deliberate work, but it must not become a tax on every normal turn. Earlier Phase-6 candidates still allowed adaptive turns to acquire a visible TaskPlan after enough substantive capability/effect evidence, and exposed an `Auto` mode that could promote a structurally complex request into deliberate planning.

That produced the wrong product boundary: the number of tool calls or the length/shape of a request could turn ordinary execution into a planning ritual even when the user simply wanted the Assistant to act.

The current design separates three concerns:

```text
normal agent reasoning/orchestration   always available within bounded host rules
TaskPlan                               explicit user-visible Plan mode only
EffectPlan                             typed host-owned effect preparation/execution contract
```

## 2. Product modes

The user-facing selector is now:

```text
Directo     default
            answer, inspect, read, reason and stage bounded effects without a visible TaskPlan

Plan        explicit user opt-in
            require an initial visible TaskPlan before capability/effect work
```

Internally the stable stored identities remain `adaptive` and `deliberate` for compatibility.

The former `auto` value is no longer selectable. A database row that still contains `auto` normalizes to `adaptive` for new turns. Historical immutable snapshots containing `auto` remain readable so already persisted data is not invalidated.

Planning mode never changes:

```text
ACL / record rules
capability availability
risk/effect metadata
policy or approval
ExecutionAuthority
write barrier
verification/recovery
```

It is orchestration/presentation behavior, not an autonomy profile.

## 3. Direct mode semantics

Direct mode does **not** mean “one operation only” and it does not mean “no reasoning”. It means no user-visible TaskPlan is manufactured unless the user selected Plan.

Valid Direct examples include:

```text
greeting / simple explanation
 -> final answer

quotation count
 -> effective schema if needed
 -> bounded aggregate
 -> final answer

create a test quotation for Demo
 -> look up Demo
 -> create Demo if absent
 -> stage/create the quotation
 -> verify according to the normal EffectPlan lifecycle
 -> final answer
```

Those operations may require several `NextDecision` cycles or several capabilities. Their count never promotes the turn into visible planning.

A more difficult request may still use additional retrieval, reasoning or capabilities in Direct mode. If the user wants the work represented and maintained as a visible multi-step plan, they select Plan explicitly.

## 4. Complexity signal

`measure_task_complexity()` remains as a bounded 0..8 structural signal derived from immutable request/screen properties. It is retained for diagnostics and future eval-driven reasoning-depth work.

It no longer activates Plan mode.

This distinction matters: reasoning effort, tool use and visible planning are different product controls. A future adaptive reasoning policy may use measured evidence to choose a provider reasoning effort or fast path, but it must not silently recreate a visible TaskPlan merely because the prompt is long or contains several list items.

## 5. Immutable turn strategy

The per-user planning selector is captured into the existing immutable execution-settings snapshot when a turn is created.

Current settings snapshot format v3 includes:

```text
reasoning_model
reasoning_effort
autonomy_profile
planning_mode
planning_strategy
policy
```

The resolved strategy contains:

```text
requested_mode
effective_mode
complexity_score
task_plan_required
```

Changing the picker while another turn is running affects future turns, not the queued/running turn.

Legacy format-v1/v2 settings snapshots remain readable. Historical format-v3 `auto` snapshots are accepted according to their persisted strategy; legacy user preferences are normalized to Direct before a new snapshot is created.

## 6. Provider-neutral boundary

`PlanningDecisionEngine` wraps any provider decision adapter.

Conceptually:

```text
Odoo host
  -> PlanningDecisionEngine
      -> failure normalization / interactive control
          -> provider adapter (Codex today, others later)
```

The host projects bounded `host_planning_strategy` and `host_task_plan_state` items into provider context. The provider adapter separates them into trusted `host_contract` fields rather than mixing them into untrusted working data.

For a new Direct turn:

```text
task_plan_available = false
```

The Codex Structured Outputs adapter therefore removes the `task_plan_update` branch from the wire schema. This is a host-enforced contract, not just a prompt instruction.

For Plan mode:

```text
task_plan_available = true
task_plan_required = true
```

A future provider can consume the same contract without owning Odoo ACL, policy, EffectPlan or recovery semantics.

## 7. TaskPlan revision semantics

TaskPlan remains public progress rather than chain-of-thought:

```text
revision_kind: initial | progress | replan
revision_summary: short public explanation
```

Rules:

```text
initial
  revision = 1

progress
  revision increments exactly by one
  goal, step ids, titles and dependency structure stay unchanged
  state/progress may change

replan
  revision increments exactly by one
  structural changes are allowed
  requires a short public revision_summary
  requires new host-observed evidence since the previous TaskPlan
```

The host owns the exact next revision and currently legal revision kinds. A provider cannot relabel an arbitrary rewrite as an evidence-driven replan.

Existing turns that already contain a TaskPlan can continue their validated revision lifecycle even if the product preference model has since changed.

## 8. Deliberate mode enforcement

When the immutable effective strategy is `deliberate`, the host rejects the first `reasoning_capability_call` or `plan_step_proposal` until an initial TaskPlan exists.

This does not make TaskPlan executable. Capability discovery, validation, policy, approval, EffectPlan and recovery remain unchanged.

A direct final answer is still allowed so explicit Plan mode does not force fake planning when the provider can genuinely answer without capability/effect work.

## 9. UX

The browser picker beside the composer now presents only:

```text
Directo
Plan
```

Directo explains that the Assistant can respond, consult Odoo and chain short actions without a visible plan. Plan explains that it is for work where the user wants an explicit guide/progress structure.

Running-turn status continues to project only the latest validated TaskPlan. A structural replan can show:

```text
Plan actualizado: <revision_summary>
```

No capability arguments/results, prompts or private provider reasoning are exposed through this path.

## 10. Short-turn routing and public activity

The first provider decision still acts as the semantic route:

```text
direct answer
minimum authoritative read
bounded effect work
```

Generic reasoning activity is published lazily only after the host accepts a non-final decision. A direct model answer therefore does not render a fake Thought card.

Exact social messages additionally use a final-answer-only provider schema. They still invoke the configured provider today; that keeps response wording model-driven but means provider generation latency remains measurable even when no tool/plan work occurs.

## 11. Latency boundary

The planning repair removes artificial TaskPlan decisions, but it does not by itself solve all short-turn latency.

The current `NextDecision` architecture can require multiple provider decisions for a bounded chain such as:

```text
schema -> query -> final answer
```

and the current Codex decision adapter starts an ephemeral App Server/thread for each decision. Historical timing evidence shows provider initialization/thread startup is non-zero, while model generation itself is the larger component on simple turns.

Therefore the next performance work should be measured against a small semantic latency/eval matrix and reduce unnecessary provider round-trips without weakening the host-owned capability boundary. It should not reintroduce `GENERAL / QUERY / HOW_TO / ACTION` routing or automatic visible planning.

Candidate optimizations to evaluate separately include:

- reusing one initialized App Server process during a durable Odoo turn;
- reducing technical schema/query round-trips through safe capability composition or an equivalent host-owned continuation seam;
- using model/reasoning-effort routing only when evals show a quality/latency benefit and the product preference semantics remain clear.

## 12. Coverage prepared

Updated/new deterministic coverage includes:

```text
tests/e2e/test_phase6_adaptive_planning_contract.py
tests/e2e/test_phase6_direct_mode_short_chain_contract.py
addons/odoo_ai_assistant/tests/test_planning_preferences.py
addons/odoo_ai_assistant/tests/test_turn_settings_snapshot.py
addons/odoo_ai_assistant/static/tests/assistant_planning_service.test.js
```

The contracts cover:

- Direct vs explicit Plan selection;
- legacy `auto` normalization;
- complexity remaining diagnostic only;
- Direct mode rejecting a new TaskPlan even after multiple substantive results;
- Direct mode accepting short effect chains without visible planning;
- deliberate TaskPlan requirement;
- progress-vs-replan structure and evidence requirement;
- immutable turn snapshot behavior;
- browser surface exposing only Directo/Plan.

These committed tests are not execution evidence by themselves.

## 13. Validation debt / Phase-6 boundary

The existing Phase-6 periodic debt remains:

```text
P6-REAL-MULTISTEP
P6-REAL-REPLAN
P6-REAL-EFFECT-ATOMICITY
P6-REAL-SEGMENTED-RECOVERY
P6-REAL-LOOP-BOUNDS
P6-REAL-EFFECT-JOURNAL
```

The direct-routing follow-up additionally needs a focused real smoke before latency can be called improved:

```text
hello / social final answer
capability explanation
a bounded Odoo count
short read + conditional create + second effect
explicit Plan turn
```

Phase 6 must not be marked COMPLETE until the applicable periodic regression and named real-product gates are green against one final candidate lineage. The implementation can still be reviewed and repaired before that acceptance batch.