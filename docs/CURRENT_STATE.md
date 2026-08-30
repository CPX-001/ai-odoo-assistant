# Current implementation state

Current accepted lineage:

```text
Foundation/P0-P4 accepted through 8a4432dc9852eacc422b8c794b6613c75da702a9
P5.1 accepted through f7f924ce944db86e896745fef83ea2fb6fd6583a
P5.2 accepted through b4fbb034e113a41c26db77cb274f2b3b30f6eee3
P5.3 accepted through 32e836e7789ea72f3ba0d32fe6bdabbb092f5953
P5.4 accepted through 3e2b38d68fe172cd2cf92d7794159f73476ac23d
P5.5 accepted through 8427c8849b1e1f3afa6337de1209a6027410c266
P5.6 accepted through 720102f2a13af5240c779b07cc71ee65994a87b1
P5.7 complete through 074a71c29a6a6109ae7412e7b1f9850c4449e379
P5.8 complete through 688f569d441a40a4637ad6a23f111e584e18c955
```

Phase 5 is **COMPLETE**. Its final repaired candidate passed the complete automated and real P5.8 gate chain.

Phase 6 is **IN PROGRESS**. The current P6.1/P6.3/P6.5 foundation is an implementation candidate on `main`; its new tests/gates have not yet been recorded as executed. See `research/P6_PLANNING_EFFECTPLAN_IMPLEMENTATION.md` and `research/EXECUTION_STATE.md`.

## 1. Product/deployment baseline

- Odoo 18 Community, self-hosted Linux.
- Addon: `addons/odoo_ai_assistant`, version `18.0.11.0.0` for the Phase-6 planning checkpoint.
- Embedded runtime; browser talks only to Odoo.
- Odoo/PostgreSQL own conversations, messages, turns, policy/settings snapshots, working checkpoints, effects and browser-safe state.
- Native `ir.cron` runs durable turns with bounded concurrency/backpressure.
- Business authority is always the originating effective user with `su=False`.
- Codex App Server is the current concrete reasoning provider using the host-configured primary session.
- The core agent/runtime is intentionally provider-neutral so later providers can implement the same port.

## 2. Provider-neutral agent loop

ADR-019/current code owns orchestration. The provider returns exactly one strict `NextDecision` per call:

```text
final_answer
task_plan_update
reasoning_capability_call
plan_step_proposal
```

The host owns capability resolution, schema validation, budgets, policy, approval, effect execution, verification and recovery semantics. Provider content is untrusted data, never authority.

Codex-specific code is limited to provider transport concerns: App Server lifecycle, Structured Outputs translation, model/reasoning options, provider failures and steer/interrupt behavior.

## 3. TaskPlan vs EffectPlan

Phase 6 now separates product planning from executable effects.

### TaskPlan

A `TaskPlan` is user-visible structured progress:

```text
goal
revision
1..12 steps
  step_id
  title
  state: pending | in_progress | completed | blocked | skipped
  depends_on
```

Properties:

- no capability name or arguments;
- no approval or execution authority;
- no private chain-of-thought;
- host reparses every revision;
- first revision is `1`; later updates must be exactly `+1`;
- durable in the private working transcript;
- latest validated revision is projected to terminal/approval browser responses;
- browser renders it separately from effect approval and explicitly says actions are authorized separately.

A TaskPlan update cannot clear a terminal policy/authority failure or reset a failing capability streak.

The richer P6.2 adaptive/deliberate/auto strategy and dedicated running-turn live TaskPlan stream are not yet claimed.

### EffectPlan

The product host now allows up to **5** typed effect steps. Legacy/custom callers remain single-step unless they receive the Phase-6 policy opt-in.

Each step retains:

```text
step_id / depends_on
capability + version
validated arguments
preview
risk / effect / approval
precondition + binding fingerprints
result + verification
semantic correlation keys
```

Current provider proposals are accumulated in deterministic order; each later proposal depends on the previous one. No generic script/program replaces `CapabilityDefinition` steps.

## 4. Current effect lifecycle

For the current Odoo-local plan capabilities:

```text
provider proposes distinct typed steps
 -> host validates and accumulates
 -> prepare / preview every step
 -> policy / approval
 -> revalidate capability/version/binding/preconditions
 -> one durable write barrier for the current Odoo-local recovery unit
 -> execute each step with ExecutionAuthority.PLAN under effective user
 -> verify each step
 -> authoritative verified-effect receipt
 -> PLAN authority removed
 -> optional read-only post-effect reasoning / TaskPlan progress update
 -> natural final answer
```

`CapabilityPlanService` uses plan format v2 and still accepts prepared format-v1 data for compatibility.

Existing P5.8 explicit HOST-only compensators work in reverse order over eligible completed plans. They are useful recovery infrastructure but do not replace the P6.4 segmented/external-effect design.

No claim is made that future external/non-transactional effects are atomic.

## 5. Budget families

Agent resource limits are no longer one undifferentiated tool counter. The host resolves:

```text
SafetyBudget
  effect-step ceiling
  consecutive-failure ceiling

ExplorationBudget
  provider decisions
  capability calls

CostBudget
  provider-decision ceiling (initial enforceable proxy)

LatencyBudget
  provider-decision ceiling (initial enforceable proxy)

ResponseBudget
  transcript bytes
  result bytes
```

The effective provider-decision ceiling is the minimum applicable host ceiling. Remaining budget values are sent to the provider as bounded context only; enforcement remains host-side. `effect_steps` reports remaining capacity.

Scheduler concurrency remains a separate Phase-5 resource concern.

## 6. Capability framework

`CapabilityDefinition` remains the atomic executable contract. Current core providers include:

```text
assistant_preferences
odoo_query
odoo_actions
odoo_batch
odoo_runtime
odoo_navigation
odoo_compensations (HOST-only inverses)
odoo_unarchive
```

No unrestricted ORM methods, SQL, Python, filesystem, shell or sudo authority is exposed to the model.

Future Skills/CapabilityProvider/ContextProvider/EvidenceProvider work should extend this framework rather than introduce a parallel tool runtime.

## 7. Conversation/settings/live UX retained from Phase 5

Accepted Phase-5 behavior remains authoritative:

- per-conversation frontend turn scopes;
- concurrent independent chats within capacity;
- one active causal turn per conversation;
- immutable per-turn model/reasoning/policy/context snapshots;
- durable reconnect/replay;
- separate public activity, readable reasoning summary and answer-delta channels;
- semantic business-facing activity grouping rather than a raw tool lifecycle dump;
- interactive stop and same-turn correction/redirect;
- approval supersession on correction;
- contextual Odoo navigation references with fresh revalidation;
- one authoritative final Assistant message;
- verified-receipt post-effect continuation;
- explicit safe compensation for supported reversible operations.

Raw provider reasoning/private chain-of-thought is never a public activity surface.

## 8. Provider abstraction

The intended provider seam is:

```text
Odoo host / AgentTurnService
          |
          v
   NextDecisionEngine
      /    |     \
   Codex  future  future
  adapter adapter adapter
```

Core logic that must remain provider-neutral includes:

```text
TaskPlan / EffectPlan
capabilities
budgets
ACL/policy/approval
write barrier
execution / verification
working transcript
failure/recovery certainty
```

Provider adapters may specialize wire schemas, streaming, authentication/session transport, model knobs and provider-specific error mapping.

## 9. Retrieval/RAG and technical operations

There is still no general embedded Evidence/RAG provider. Later retrieval should combine live Odoo/runtime/schema/configuration, source/XML, logs, company knowledge/files, lexical/semantic retrieval and web evidence according to question type.

Not currently exposed as generic reasoning authority:

```text
module install/update
odoo.conf modification
service/process restart
PostgreSQL administration
source-code modification
generic command execution
general arbitrary network access
```

Later privileged technical operations require explicit high-level capabilities and a privilege-boundary design.

## 10. Validation state

Accepted P5.8 evidence remains:

```text
research/evidence/phase5/2026-08-30/P5.8-REAL-ACCEPTANCE-688f569.md
```

The current Phase-6 implementation contains new deterministic tests for TaskPlan, multi-step EffectPlan, budget separation and Codex wire translation, but these have **not yet been recorded as executed on the final candidate**.

No P6 HARD real gate is currently recorded PASS.

Formal cursor:

```text
P0 COMPLETE
P1 COMPLETE
P2 COMPLETE
P3 COMPLETE
P4 COMPLETE
P5 COMPLETE
P6 IN_PROGRESS
  P6.1 TaskPlan vs EffectPlan            IMPLEMENTED CANDIDATE
  P6.2 adaptive/deliberate modes         NOT STARTED
  P6.3 bounded multi-step EffectPlan     IMPLEMENTED CANDIDATE
  P6.4 atomic vs segmented effects       NOT STARTED
  P6.5 separate budgets                  FOUNDATION IMPLEMENTED CANDIDATE
  P6.6 EffectJournal                     NOT STARTED
```

The next meaningful boundary is validation of the combined P6.1/P6.3/P6.5 checkpoint before building segmented recovery/journaling on assumptions that have not been exercised in Odoo/Codex.
