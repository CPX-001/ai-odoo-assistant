# Current implementation state

This document summarizes what the supported Odoo 18 addon on `main` currently implements. For the exact roadmap
cursor and unexecuted gates, use `research/EXECUTION_STATE.md`.

## Accepted lineage

```text
Foundation/P0-P4 through 8a4432dc9852eacc422b8c794b6613c75da702a9
P5.1 through f7f924ce944db86e896745fef83ea2fb6fd6583a
P5.2 through b4fbb034e113a41c26db77cb274f2b3b30f6eee3
P5.3 through 32e836e7789ea72f3ba0d32fe6bdabbb092f5953
P5.4 through 3e2b38d68fe172cd2cf92d7794159f73476ac23d
P5.5 through 8427c8849b1e1f3afa6337de1209a6027410c266
P5.6 through 720102f2a13af5240c779b07cc71ee65994a87b1
P5.7 through 074a71c29a6a6109ae7412e7b1f9850c4449e379
P5.8 through 688f569d441a40a4637ad6a23f111e584e18c955
P6 final acceptance through 0b1bcab39b71dfbe02526cda7cf7ac8e218ac4b0
```

Phase 5 and Phase 6 are **COMPLETE**. The final Phase-6 regression evidence is
`research/evidence/regression/2026-08-31/FULL-REGRESSION-fc022a6.md`.

Phase 7 has started only at the provider-extension foundation. Live Phase-7 capability-provider integration is
currently paused behind the Product Behavior Evals v1 gate described in `research/PRODUCT_BEHAVIOR_EVALS_V1.md`.

## 1. Product/deployment baseline

- Odoo 18 Community, self-hosted Linux target.
- Supported addon: `addons/odoo_ai_assistant`, current manifest version `18.0.13.4.0`.
- Embedded runtime; browser talks only to Odoo.
- Odoo/PostgreSQL own conversations, messages, immutable turn settings, working checkpoints, effects, recovery
  state, EffectJournal and browser-safe live state.
- Native `ir.cron` runs durable turns with bounded concurrency/backpressure.
- Business authority is the originating effective user with `su=False`.
- Codex App Server is the current concrete reasoning provider using the host-configured primary session.

## 2. Provider-neutral host loop

The reasoning provider returns one strict `NextDecision` at a time:

```text
final_answer
task_plan_update
reasoning_capability_call
plan_step_proposal
```

The host owns capability resolution, schemas, budgets, planning rules, EffectPlan preparation, policy, approval,
execution, verification and recovery. Provider output is untrusted input, not execution authority.

Codex-specific code remains below that boundary and owns transport/schema translation, App Server lifecycle,
model/reasoning settings, safe readable-summary handling and provider error mapping.

## 3. Current planning behavior

The accepted Phase-6 runtime distinguishes:

```text
Direct/adaptive
  default strategy
  no TaskPlan for new Direct turns
  may perform multiple reads/effects without visible planning

Plan/deliberate
  explicit planning strategy
  initial TaskPlan required before capability/effect work when planning is actually applicable
```

TaskPlan is public orchestration/progress only and has no effect authority. EffectPlan is a separate host-owned typed
proposal/execution contract.

### Known product change queued by the Product Behavior gate

Current `main` still represents planning mode as a persisted per-user preference and the composer `+` control keeps
Plan active until toggled. The approved target is instead a **one-shot Plan tag/chip for the next submitted turn**:
select Plan -> show removable composer tag -> capture deliberate planning for that turn -> clear the tag -> following
turn is Direct unless selected again.

This is not yet an implementation claim. It is a required pre-live-P7 product change.

## 4. Capabilities currently shipped

`CapabilityDefinition` remains the atomic executable contract. Core provider families include:

```text
odoo_query       schema-first live records/aggregates
odoo_actions     bounded create/patch/archive/delete + explicit sale-order confirmation
odoo_batch       bounded multi-record mutation
odoo_runtime     narrow effective runtime identity facts
odoo_navigation  host-resolved Odoo record/model/action/view/menu/setting references
odoo_unarchive   explicit unarchive action
odoo_compensations HOST-only verified safe reversion helpers
assistant_preferences conversation language/autonomy preference operations
```

No unrestricted ORM method, SQL, Python, filesystem, shell or sudo authority is exposed to the model.

Generic CRUD is a fallback. When an explicit semantic business capability exists, the agent should prefer it; sale
order confirmation is the current canonical example.

## 5. Reads and current-installation truth

Frequently changing Odoo business truth is read live under current ACLs and record rules. The query path supports
bounded model discovery, effective schema, record reads and server-side aggregation.

A general question that does not depend on this installation can be answered directly without Odoo tools. A claim
about this installation should be grounded in current local evidence.

## 6. Conversation context and current memory boundary

P5.6 `ConversationContextManager` is accepted and Odoo-owned. It carries a bounded causal view containing:

```text
recent messages
rolling deterministic summary
active record/model references
verified effect references
evidence reference slots
session settings
```

It supports reconnect/follow-up continuity and isolates conversations. It is **not** a freshness-aware cache of live
business facts. Previous Assistant prose alone is not enough to skip authoritative verification of mutable Odoo data.

The Product Behavior gate will measure repeated same-chat fact queries before deciding whether any additional cache
is justified. A future cache that can replace a live read must bind security/company scope, query identity,
provenance and freshness/invalidation; Phase 8 Evidence/Freshness is the natural owner unless a smaller safe Odoo
optimization proves sufficient.

## 7. Bounded EffectPlan and recovery

The host supports up to 5 typed effect steps with per-step capability/version/args, preview, preconditions, risk,
approval, binding, execution result and verification.

Recovery modes are host-derived:

```text
odoo_atomic
segmented
external
```

Persisted in-flight effects are never blindly replayed. Stop/correction state is rechecked at recovery boundaries.

## 8. EffectJournal and compensation

`odoo.ai.effect.journal` stores bounded short-lived recent effect evidence with a 7-day TTL and classifications:

```text
reversible
reconstructable
irreversible
external_or_unknown
```

It is not a backup. Existing host-only compensation for safe patch/archive/unarchive effects revalidates permissions
and optimistic state before restoring anything. Later user edits produce a conflict instead of being overwritten.

## 9. Budgets

The host separates:

```text
SafetyBudget
ExplorationBudget
CostBudget
LatencyBudget
ResponseBudget
```

Provider-visible remaining values are context only. Enforcement remains host-side.

## 10. User-facing chat behavior already implemented

Current accepted product path includes:

- durable conversations/turns and non-blocking multichat;
- per-turn model/reasoning/planning/policy settings snapshots;
- model family/variant + reasoning effort + autonomy controls;
- conversation language/autonomy preference capabilities;
- semantic public activity and bounded readable reasoning summaries;
- typed Odoo navigation references with fresh revalidation;
- Stop and same-turn corrections/interventions;
- partial interrupted answer preservation;
- approval/recovery UX;
- safe reversion when host-declared compensation is available;
- answer-delta live channel plus authoritative final reconciliation.

## 11. Streaming: implemented path, current regression hypothesis

The runtime still contains the intended provisional answer path:

```text
Codex item/agentMessage/delta
 -> StructuredFinalAnswerDeltaExtractor
 -> answer.delta
 -> persisted Odoo live event
 -> browser polling/live cursor
 -> provisional streamingText
 -> final reconciliation
```

Historical Phase-4 real gates proved first-delta/parity/cancel/UTF-8 behavior on the Phase-4 checkpoint. However the
user currently observes that the UI often remains in thinking state and then shows the full answer at once. The
Phase-6 final periodic regression did not rerun the real first-delta gate, so this is an open **current regression
hypothesis**, not contradicted by the historical P4 evidence.

`research/PRODUCT_BEHAVIOR_EVALS_CODEX_HANDOFF.md` requires timing the provider delta, extractor emission, Odoo live
commit, browser first delta and final completion before repairing the actual bottleneck. Fake post-completion chunking
is not acceptable streaming.

## 12. Semantic activity presentation

Normal UI is designed to show human work classes such as consulting/filtering records, preparing an action or
verifying results. Raw capability ids/arguments and provider-private reasoning are hidden by default.

Accepted detail profiles include compact/normal/detailed/diagnostic. Diagnostic may expose structural metadata and
timings but still must not expose private reasoning/secrets.

The Product Behavior contract further freezes that settled activity belongs **above** the final answer it explains,
and zero-tool direct answers should not leave a fake settled reasoning artifact.

## 13. Permissions/personas

Product behavior must be validated primarily as ordinary internal Odoo users, not only admin. Odoo access rights and
record rules remain the authority for model/record visibility.

The new product eval suite defines:

```text
business_user  normal internal app user
limited_user   internal user with deliberate record/model restrictions
admin_user     settings/runtime administration cases
```

Limited-user UX should explain permission limitations without leaking inaccessible data. For mixed result sets it
may return visible records and state that additional matching data could not be included due to access restrictions.

## 14. P7 provider-extension foundation

An isolated P7.1 foundation now exists:

```text
CapabilityProvider
CapabilityProviderStatus
Odoo-registry provider discovery
registry composition + provider provenance
optional-provider failure isolation
duplicate provider/capability conflict rejection
```

The marker is trusted installed Odoo model code, not arbitrary Python-package discovery. The foundation is documented
in `research/P7_MINI_FRAMEWORK_IMPLEMENTATION.md`.

At the current cursor it has not yet been wired into the live effective capability catalog and its focused local
deterministic test has not yet been recorded PASS.

## 15. Pre-live-P7 Product Behavior gate

Before live P7 catalog integration resumes, implement and execute:

```text
research/PRODUCT_BEHAVIOR_EVALS_V1.md
research/PRODUCT_BEHAVIOR_EVALS_CODEX_HANDOFF.md
```

The v1 catalog contains 54 scenarios across Spanish, Catalan and English and covers direct/general answers, live Odoo
facts, ACLs, navigation, writes, approvals, batch UX, streaming, activity order, Stop/correction, multichat,
preferences and no-overclaim self-description.

It also requires per-provider/per-capability timing so tool anomalies are visible independently from model latency.

## 16. Future module/source HOW_TO

The product target remains installation-aware support for third-party/custom addons: the Assistant should eventually
be able to answer whether an installed module supports a function and how to use it by inspecting current module,
source/XML/runtime evidence rather than relying on hard-coded knowledge.

That source/module diagnosis is intentionally not a v1 executable product eval yet because the planned Phase-8
source/XML evidence layer is not implemented.

## 17. Current formal status

```text
P0 COMPLETE
P1 COMPLETE
P2 COMPLETE
P3 COMPLETE
P4 COMPLETE
P5 COMPLETE
P6 COMPLETE
P7 IN_PROGRESS / LIVE INTEGRATION PAUSED
  P7.1 provider extension foundation LANDED / LOCAL VALIDATION REQUIRED
  Product Behavior Evals v1 IMPLEMENTATION + REAL BASELINE REQUIRED
  P7.1 live catalog wiring BLOCKED
  P7.2+ NOT STARTED
```

Use `research/EXECUTION_STATE.md` for the exact next action and stop rule.
