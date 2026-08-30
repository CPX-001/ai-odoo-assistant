# Architecture

Current product architecture for `ai-odoo-assistant`. For the implementation snapshot see `CURRENT_STATE.md`; for target product behavior see `PRODUCT_VISION.md`; accepted ADRs remain decision authority.

## 1. Deployment unit

The managed application is the Odoo 18 Community addon `odoo_ai_assistant`.

```text
Browser / OWL
    |
    | authenticated Odoo JSON/RPC
    v
Odoo 18 + odoo_ai_assistant
    |
    +-- Odoo PostgreSQL
    +-- native ir.cron turn workers
    +-- <data_dir>/odoo_ai_assistant/*
    +-- Codex App Server subprocess per provider decision/turn path
```

The supported runtime does not require the retired FastAPI/Uvicorn sidecar, second Assistant database, internal sidecar HTTP port or shared machine secret.

Future privileged host operations may require a narrow local privilege broker/helper. That is not the retired Assistant sidecar and cannot be introduced without a dedicated ADR defining its authority and installation boundary.

## 2. Authority boundary

Odoo/host code is authoritative for:

- authenticated user and allowed companies;
- ACLs, record rules and field access;
- model/schema visibility;
- conversation/turn state;
- capability/provider discovery and configuration;
- planning strategy and immutable turn settings;
- autonomy/policy/technical access profile;
- agent budget ceilings;
- approval state;
- TaskPlan transition rules;
- EffectPlan preparation/execution/verification/recovery;
- recovery-unit classification and EffectJournal state;
- public activity/failure/progress projection;
- future Evidence/Knowledge access policy;
- scheduler capacity/backpressure.

The reasoning provider is not authority. It may reason broadly and request supported operations, but each operation is resolved against current host state.

Business capabilities execute under the effective user and must not gain `su=True` as a shortcut. Host-internal infrastructure may use privileged mechanics only for narrowly defined internal coordination/operations.

## 3. Durable turn model

A browser submit persists the user message and `odoo.ai.turn` before long reasoning begins.

Current turn processing uses:

- queued/running/approval/terminal states;
- lease token and expiry;
- bounded attempts;
- cancellation;
- stale-turn recovery;
- two native cron runner slots;
- an administrator-configurable logical execution ceiling currently bounded to those two physical slots;
- a short host-internal PostgreSQL advisory lock for race-safe admission/claim;
- one active causal turn per conversation;
- cross-user anti-starvation ordering;
- post-release scheduler wake-up;
- bounded aggregate scheduler diagnostics.

The scheduler claim transaction uses `READ COMMITTED` locally before acquiring the advisory lock so a worker that waited for another claim observes the previous committed claim. Provider/business execution never holds the scheduler coordination lock.

Excess work remains durable `queued`; scheduler saturation is not treated as a turn failure. `running` and `cancel_requested` consume execution capacity. `awaiting_confirmation` releases worker capacity while continuing to block later turns in the same conversation. `recovery_required` remains non-replayable but is terminal for scheduler eligibility.

The current physical pool still has two cron slots. P5.2 makes capacity/backpressure explicit for that pool; future measurement/provider support may justify a larger runner pool without changing turn authority or recovery semantics.

P5.2 is implemented and accepted through its batched deterministic/Odoo/regression/real gates. See
`research/P5.2_SCHEDULER_IMPLEMENTATION.md` and
`research/evidence/phase5/2026-08-29/P5.2-REAL-ACCEPTANCE-b4fbb03.md`.

## 4. Concurrency boundary

A running turn is background server work, not a browser lock.

P5.1 established per-conversation frontend execution scopes. Chat A may continue in the background while the user opens or submits Chat B; late A activity/stream/failure updates remain owned by A, and model/autonomy/planning selectors affect future turns rather than mutating A's captured snapshot.

P5.2 extends the same product rule into backend scheduling:

```text
Chat A turn running
   |
   +-- user may switch to Chat B
   +-- Odoo remains usable
   +-- selectors/settings remain usable
   +-- Chat B may submit/run when capacity exists
   +-- later Chat A turn waits for A's unresolved predecessor
   +-- excess global work remains queued under backpressure
```

The ordering rule is one active causal turn per conversation, multiple conversations in parallel up to effective capacity. This prevents racing two messages against the same unresolved conversation context while still allowing real multitasking.

Scheduler fairness prefers users consuming fewer active slots, then the least recently served waiting user, then FIFO within that service order. One user may still use spare capacity when nobody else is waiting.

A turn captures the execution settings/policy/model/profile/planning strategy it requires. UI changes made while it runs affect future turns rather than changing the running turn retroactively.

## 5. Agent runtime

`AgentTurnService` is the current host loop. A provider-neutral reasoning seam returns one validated `NextDecision` at a time.

Conceptually:

```text
provider decision
  -> final_answer
  OR task_plan_update
  OR reasoning_capability_call
  OR plan_step_proposal
```

`PlanningDecisionEngine` sits above provider adapters. `adaptive`, `deliberate` and `auto` are orchestration modes captured per turn; they never grant capability or write authority. Deliberate mode requires an initial public TaskPlan before capability/effect requests, while structural replans require new host-observed evidence.

The host validates capability identity, schema, effective availability and budget families. READ results/errors become bounded private working items and may drive another provider decision.

The action path accumulates a bounded typed EffectPlan of up to five steps. Every step remains one `CapabilityDefinition`; there is no generic provider-authored program, arbitrary ORM method, SQL or shell execution surface.

After verified effects, PLAN authority is removed. A verified receipt may return to read-only reasoning so the provider can synthesize the natural final answer without replaying the effect.

## 6. Capability framework

`CapabilityDefinition` is the atomic executable contract. `CapabilityRegistry` creates effective views and `CapabilityExecutor` executes resolved definitions.

Current core providers include:

```text
runtime/capabilities/providers/
  odoo_query.py
  odoo_actions.py
  odoo_batch.py
  odoo_runtime.py
  odoo_navigation.py
  odoo_compensations.py
  odoo_unarchive.py
```

Future composition is additive:

```text
CapabilityProvider
  -> Skill / Bundle
  -> CapabilityDefinition
  -> optional ContextProvider / EvidenceProvider
```

No parallel chat/MCP/automation registry is introduced.

The framework is not permanently restricted to CRUD. Explicit future capabilities may wrap source reads, logs, Odoo module/config operations, web evidence or approved host operations when their schemas, profiles, policy, privilege boundary and verification are defined.

See `CAPABILITY_FRAMEWORK.md`.

## 7. Context architecture

Current turn input includes bounded user/screen/conversation/capability context plus immutable per-turn model, reasoning, policy and planning settings. Screen context is an untrusted navigation hint; user/company/permissions are reconstructed server-side.

The target Context Orchestrator keeps a small reliable base and resolves additional context just in time:

```text
BaseContext
  user/company/lang/tz
  Odoo/database/version
  current screen/record hints
  conversation state
  Assistant manifest summary

+ ContextProviders
  module/schema/view/action
  domain-specific context
  source/log/runtime context
```

Global potential knowledge is not dumped into every prompt.

## 8. Evidence/retrieval architecture

There is currently no general embedded RAG provider.

Target:

```text
EvidenceProvider
  -> normalized Evidence
      provenance / locator / fingerprint / freshness
      bounded data/excerpt / access scope / citation
```

Evidence sources include live Odoo/runtime facts, source/XML, logs, company Knowledge, lexical/semantic indexes and future web/connectors.

Live business records remain live Odoo authority. Retrieved content is never policy.

See `KNOWLEDGE_INDEX.md`.

## 9. Provider boundary

Codex App Server is the primary current provider and is owned as a local subprocess by the Odoo runtime identity. Credentials remain provider-owned in one host-configured primary `CODEX_HOME` consumed by the installation. Odoo users share that provider identity and quota, never Odoo business authority or conversation data.

The product contract is provider-neutral. TaskPlan, EffectPlan, budgets, recovery units, EffectJournal, ACL/policy/approval and execution remain above the provider adapter. Codex-specific code owns App Server transport, Structured Outputs translation, provider events/errors and steer/interrupt behavior.

Future `ProviderProfile` feature negotiation may record capabilities such as structured output, tool calls, answer streaming, vision/file input, web and context support as `native`, `emulated` or `unavailable`.

Do not reduce every provider to a lowest common denominator. The Assistant manifest/UI should accurately expose effective features.

## 10. Live public activity, TaskPlan and answer projection

Current `main` includes accepted P3/P4 production implementation for public activity and answer streaming plus the Phase-6 candidate TaskPlan projection.

### Public activity

Runtime lifecycle is projected into closed bounded `PublicTurnEvent` data and persisted in an independent `odoo.ai.turn.live.event` transaction. This allows a second browser request to observe progress without committing the worker business transaction.

### TaskPlan

The latest validated TaskPlan is public progress data, not private reasoning. Running status exposes a bounded TaskPlan without capability arguments. The frontend keeps the highest host-validated revision and prefers the authoritative final response on equal revisions, preventing a stale live poll from hiding the terminal plan.

### Answer

Codex `item/agentMessage/delta` events are parsed only for the structured user-facing answer field. Provisional answer deltas are non-authoritative and share the independent live stream store. Final validated `NextDecision` remains authoritative.

### Browser

The current browser consumes `/odoo_ai/v1/turn/live` and `/turn/status` through Odoo-authenticated polling. Activity, TaskPlan, readable reasoning summary and answer are separate UI/data surfaces.

Polling vs SSE/bus is an optimization decision; persisted turn/live state is the authority.

## 11. Effect lifecycle and recovery units

Current bounded effect path:

```text
one or more typed proposals (max 5)
 -> host accumulate + dependency ordering
 -> prepare/preview + preconditions for every step
 -> policy/approval
 -> revalidate version/binding/preconditions
 -> recovery-unit checkpoint / write barrier
 -> execute as effective user
 -> verify each step
 -> verified receipt + EffectJournal / recovery state
 -> post-effect read/final synthesis with PLAN disabled
```

Prepared plans use current format-v3 recovery metadata while preserving format-v1/v2 execution compatibility.

Recovery units are host-derived from trusted capability metadata:

```text
odoo_atomic  consecutive Odoo-local steps intentionally sharing one transaction/recovery unit
segmented    explicit durable internal unit boundary
external     external/non-transactional unit whose in-flight interruption may remain uncertain
```

Before crossing each new durable unit the host preflights the unit, reacquires the effect lock and rechecks Stop/redirect. Completed non-final segmented units can be durably distinguished from later units. A persisted in-flight unit is never blindly replayed.

If an Odoo-local transaction is lost, the host may classify the unit as rolled back when that is actually knowable. External/non-transactional ambiguity remains `uncertain` until a dedicated recovery procedure resolves it.

## 12. Persistence

Operational state is Odoo-native:

- conversations/messages/turns;
- queue/lease/recovery state;
- scheduler service watermark (`scheduler_claimed_at`);
- failure payloads;
- TaskPlan working state;
- effect plans/receipts and recovery units;
- short-lived `odoo.ai.effect.journal` records;
- public/live event state;
- current settings/configuration.

The EffectJournal stores bounded recent before/after/receipt evidence and classification for recovery/inspection. It is not a backup, unlimited audit warehouse or chain-of-thought store; current retention is intentionally short and scheduled for cleanup.

Future ConversationContext/EvidenceLedger/KnowledgeSource subsystems should also remain Odoo-owned unless a specific ADR/evaluation demonstrates a strong reason otherwise.

Historical root migrations/Assistant SQLAlchemy DB are retired lineage.

## 13. Filesystem

`RuntimePaths.from_odoo()` derives runtime/cache/source paths below Odoo `data_dir`. The persistent provider home comes from the absolute host `CODEX_HOME`; when absent, the managed `<data_dir>/odoo_ai_assistant/codex` path remains a compatible fallback. Current code validates external homes and rejects unsafe managed paths/symlinks.

Future source/host capabilities must use explicit approved roots/locators; a reasoning provider does not gain arbitrary filesystem authority merely because Odoo can read files.

## 14. Technical access

Autonomy and technical reach are different axes.

Target technical profiles:

```text
Business/User
Developer/Operator
```

Developer operations such as module update, Odoo config patch, service restart or PostgreSQL diagnostics require specialized capabilities. Privileged OS operations require a new ADR/privilege boundary; `Full access` autonomy alone cannot grant them.

## 15. Evolution rule

Before adding a subsystem:

1. reuse current durable turn/capability/policy/recovery infrastructure;
2. keep model-facing description separate from host authority;
3. define deterministic + agentic + real blocking gates;
4. use an ADR for changes to deployment/privilege/persistence/effect invariants;
5. borrow tested Odoo patterns where useful without adding dependencies by reflex.

Useful references include OCA `queue_job` for bounded background concurrency, OCA `ai_tool` for reusable UI/tool declaration, and Apexive for provider/Knowledge/domain-tool breadth. They are implementation references, not authority replacements.

## 16. Validation architecture

The repository uses risk-based incremental validation during implementation and batches expensive broad/real checks into explicitly named periodic checkpoints.

```text
changed contract
 -> focused unit/contract tests when practical
 -> directly affected Odoo or browser boundary
 -> accumulate broad/real validation debt
 -> periodic full regression on one exact candidate SHA
```

The current Phase-6 candidate is implementation-complete but not accepted. The canonical periodic runbook is `research/PERIODIC_FULL_REGRESSION_RUNBOOK.md`; it combines deterministic current contracts, complete addon tests, complete HOOT and all accumulated named real-product gates.

A passing historical phase or committed test file is not evidence that the current candidate passed. Required but unexecuted gates remain explicit validation debt.
