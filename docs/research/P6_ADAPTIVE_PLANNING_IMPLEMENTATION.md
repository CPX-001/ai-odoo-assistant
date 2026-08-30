# Phase 6.2 adaptive/deliberate planning implementation

Date: 2026-08-30  
Status: **IMPLEMENTED CANDIDATE — PERIODIC VALIDATION REQUIRED**

This record closes the remaining Phase-6 implementation block without claiming any unexecuted HARD gate as PASS.

## 1. Problem

The existing TaskPlan was correctly separated from EffectPlan authority, but every turn still used the same orchestration behavior. Phase 6.2 needs deeper planning for difficult work without forcing every simple question through a heavyweight planning ritual or moving planning authority into Codex.

The implementation therefore adds a provider-neutral host strategy above `NextDecisionEngine`.

## 2. Planning modes

The user preference is:

```text
adaptive    default
            begin directly; TaskPlan remains available when useful

deliberate  explicit Plan mode
            require an initial visible TaskPlan before the first reasoning capability or effect proposal

auto        host resolves adaptive vs deliberate from bounded structural complexity signals
```

`auto` deliberately does **not** classify business intent. Current signals are small deterministic properties of the immutable request/screen snapshot such as request length/structure and selected-record count.

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

It is an orchestration preference, not an autonomy profile.

## 3. Immutable turn strategy

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

The resolved strategy contains only:

```text
requested_mode
effective_mode
complexity_score
task_plan_required
```

Changing the picker while another turn is running therefore affects later turns, not the already queued/running turn.

Legacy format-v1/v2 settings snapshots remain readable.

## 4. Provider-neutral boundary

`PlanningDecisionEngine` wraps any provider decision adapter.

Conceptually:

```text
Odoo host
  -> PlanningDecisionEngine
      -> failure normalization / post-effect restrictions
          -> provider adapter (Codex today, others later)
```

The host projects one bounded `host_planning_strategy` item into provider context. It is not persisted as user/model transcript content and grants no authority.

Codex remains the current transport implementation. A future provider can receive the same strategy and return the same `NextDecision` contract without copying the Odoo planning, ACL, EffectPlan or recovery loop.

## 5. TaskPlan revision semantics

TaskPlan keeps being public progress rather than chain-of-thought. The current provider contract adds:

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

Accepted evidence kinds for a structural replan are currently bounded host transcript facts such as a capability result/error or a verified effect receipt. A provider cannot relabel an arbitrary rewrite as evidence-driven replan.

Legacy persisted TaskPlans without the new fields remain readable and normalize to `initial`/`progress` semantics.

## 6. Deliberate mode enforcement

When the immutable effective strategy is `deliberate`, the host rejects a first `reasoning_capability_call` or `plan_step_proposal` until an initial TaskPlan exists.

This does not make TaskPlan executable. The normal capability catalog, validation, policy, approval, EffectPlan and recovery layers remain unchanged.

A direct final answer is still allowed so the host does not force fake planning for a response that genuinely needs no capability/effect work.

## 7. Live and terminal TaskPlan UX

The browser now has a planning picker beside the existing composer controls:

```text
Adaptativo
Plan
Auto
```

The running turn status projects only the latest validated TaskPlan. The frontend polls this bounded public projection while the active turn runs and renders the plan separately from effect approval.

For a structural replan the view can show:

```text
Plan actualizado: <revision_summary>
```

No capability arguments/results, prompts or private provider reasoning are exposed through this path.

Terminal/approval responses accept both legacy TaskPlan payloads and the current `revision_kind` / `revision_summary` contract. The UI normalizes both forms and reconciles live vs terminal state by revision: the newer revision wins, while the authoritative final response wins an equal-revision race. A final status refresh closes the case where the last TaskPlan revision is persisted immediately before turn completion.

## 8. Coverage committed

New/updated coverage includes:

```text
tests/e2e/test_phase6_adaptive_planning_contract.py
addons/odoo_ai_assistant/tests/test_planning_preferences.py
addons/odoo_ai_assistant/tests/test_turn_settings_snapshot.py
addons/odoo_ai_assistant/static/tests/assistant_planning_service.test.js
addons/odoo_ai_assistant/static/tests/phase6_task_plan_final_contract.test.js
```

The contracts cover adaptive/deliberate/auto selection, no authority escalation, deliberate TaskPlan requirement, progress-vs-replan structure, evidence-required structural replan, legacy TaskPlan compatibility, immutable turn snapshot, bounded live browser replan data and terminal/live revision reconciliation.

These committed tests are not evidence of execution by themselves.

## 9. Validation debt / Phase-6 boundary

P6.2 adds the remaining named real gate:

```text
P6-REAL-REPLAN
```

It joins the already accumulated periodic Phase-6 validation debt:

```text
P6-REAL-MULTISTEP
P6-REAL-REPLAN
P6-REAL-EFFECT-ATOMICITY
P6-REAL-SEGMENTED-RECOVERY
P6-REAL-LOOP-BOUNDS
P6-REAL-EFFECT-JOURNAL
```

All Phase-6 implementation areas are now present as candidates. Phase 6 must **not** be marked COMPLETE or accepted until the applicable periodic full regression and real-product gates are green against one exact candidate SHA.

The next roadmap phase remains ineligible until that checkpoint is accepted; this is now a meaningful point to spend one periodic validation batch rather than another implementation micro-gate.
