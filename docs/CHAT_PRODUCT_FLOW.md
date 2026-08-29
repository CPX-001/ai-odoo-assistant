# Chat product flow

This document describes the current embedded chat path and the next product-level chat invariants. It supersedes the retired browser/Odoo/Assistant-Service flow.

## 1. Current end-to-end path

```text
OWL Assistant panel
    |
    | Odoo authenticated JSON/RPC
    v
Odoo controllers/services
    |
    +--> conversation/message persistence
    +--> screen-context validation
    +--> account/model/policy snapshot
    |
    v
odoo.ai.turn (queued)
    |
    v
native ir.cron + lease claim
    |
    v
AgentTurnService
    |
    +--> effective CapabilityRegistry
    +--> ReasoningProvider / Codex
    +--> host capability execution
    |
    v
prepare / approval / execute / verify / failure/recovery
    |
    +--> authoritative turn result
    +--> independent live activity/answer events
    |
    v
OWL polls Odoo status + live cursor
```

The browser never calls a separate Assistant Service and never owns provider credentials or capability authority.

## 2. Submit is short and durable

Submitting a message remains a short Odoo request:

1. validate caller/message/screen hint;
2. locate/create owned conversation;
3. persist user message;
4. snapshot turn-relevant model/policy/company/context settings;
5. create durable queued `odoo.ai.turn`;
6. trigger available native runner slots;
7. return turn/conversation id and state.

Reasoning/provider work continues outside the submit request.

This means browser navigation, closing the panel or a temporary polling failure does not cancel the server turn.

## 3. Current processing concurrency

The backend queue claims work with `FOR UPDATE SKIP LOCKED`, leases and stale recovery. Phase 5.2 accepted a bounded two-slot scheduling policy with same-conversation causal ordering, cross-conversation concurrency, backpressure and fairness behavior.

The frontend/background ownership work from Phase 5.1 is also accepted: running state is scoped by turn/conversation rather than a single global chat lock, so one running conversation does not prevent normal work in another conversation.

The capacity value itself is still a product/runtime policy rather than a permanent assumption. Future provider/worker/resource constraints may change the effective ceiling without changing the durable turn contract.

## 4. Accepted non-blocking chat behavior

While Chat A runs:

```text
Chat A: running ----------------------------------> terminal
         |
         +-- user switches to Chat B
         +-- creates Chat C
         +-- changes next-turn model/autonomy/profile
         +-- continues navigating/forms in Odoo
         +-- returns later to Chat A
```

The current turn continues independently.

The history/conversation UI can expose compact background state so the user can distinguish queued/running/awaiting approval/failed/recovery/completed work.

## 5. Initial concurrency semantics

### Across conversations

Multiple conversations may have active turns concurrently up to host/provider capacity.

### Inside one conversation

There is one active **causal** turn at a time.

A second ordinary message in the same conversation must not race against an unresolved first turn and build context from a different future. Same-conversation turns preserve predecessor ordering.

Future `steer current turn` or conversation branching is separate product work and requires explicit contracts/tests.

## 6. Capacity and backpressure

Concurrency must remain configurable/observable rather than assuming two slots forever.

Capacity policy should eventually include:

```text
installation turn ceiling
provider concurrency/rate limits
Odoo worker/cron capacity
CPU/RAM/process constraints
per-user fairness
interactive-vs-background priority
```

When capacity is full:

- submit remains successful if the work can be queued safely;
- turn state remains `queued`;
- the rest of the UI remains usable;
- the product may show queue position/wait state when reliable;
- no busy overlay/global disabled state is used as backpressure.

OCA `queue_job` remains a useful reference for channels/capacity/background recovery, but current native queue semantics are retained unless an ADR/evaluation justifies a dependency/replacement.

## 7. Settings while a turn is running

Turn-sensitive settings are snapshots, not live mutable references.

Phase 5.3 accepted this rule for model/policy/autonomy values required by a turn. The target applies the same principle to future technical profile/strategy/config versions.

Therefore:

```text
Turn A queued with model X + Balanced
user changes UI to model Y + Autonomous
Turn A continues with X + Balanced
future Turn B uses Y + Autonomous
```

The user is free to open/change selectors while A runs.

Approval/rejection is not a normal setting edit; it is an explicit transition bound to A's prepared effect and may resume A.

Phase 5.7 adds conversation-scoped preference mutation as a later explicit host-owned capability; administrator/system ceilings remain authoritative.

## 8. Public activity

Phase 3 public activity is accepted. The current runtime has a closed bounded `PublicTurnEvent` contract and an independent browser-safe live store that is intentionally separate from the worker business transaction.

That foundation solves durability, reconnect, redaction and visibility, but the current visible presentation is still too close to capability lifecycle events. A call can produce both `started` and `completed` rows with the same capability title, and repeated reads can therefore look like a technical event log.

Public activity remains trusted host projection and is **not** private provider reasoning. It must not expose prompts, raw arguments/results, credentials, stdout/stderr or chain-of-thought.

The target semantic presentation is specified in [`research/P5.8_SEMANTIC_ACTIVITY_UX.md`](research/P5.8_SEMANTIC_ACTIVITY_UX.md): stable operation correlation, semantic work-item reduction, readable provider reasoning summaries only where safely supported, typed references, configurable detail and full Odoo-language localization.

## 9. Answer streaming

Phase 4 structured provisional answer streaming is accepted.

Codex `item/agentMessage/delta` is parsed into the provisional answer channel. Provisional output is not authority; the final validated turn result reconciles it.

Browser channels are conceptually:

```text
activity.event
answer.delta
turn.final
turn.failure
```

Future semantic activity may add a higher-level projection/channel, but it must not make transport the authority contract.

## 10. Background turn observation

The browser may detach from a turn and later resume from Odoo state.

Frontend state is keyed by turn/conversation rather than one global stream buffer.

The visible chat consumes live updates at normal cadence. Background chats may use lighter periodic refresh/badges to avoid multiplying polling cost indefinitely.

A later Odoo bus/SSE transport may reduce polling overhead, but transport is not the durability contract.

## 11. Effects and approval

A user's natural-language request is intent, not authorization.

Current action path:

```text
model proposal
 -> host prepare/preview/preconditions
 -> current policy
 -> approval if required
 -> revalidate
 -> write barrier
 -> execute
 -> verify
 -> receipt / recovery
```

Current implementation still supports one canonical effect step. The future product supports bounded multi-step `EffectPlan` while retaining the same host controls.

Approval UX should stay actionable outside any reasoning/activity disclosure. A future semantic activity item or TaskPlan step can reference the approval, but the user must not need to expand progress history to approve/reject it.

## 12. Post-effect conversation

Phase 5.5 post-effect reasoning is accepted.

Current successful effect path is conceptually:

```text
execute
 -> verify
 -> append verified receipt to working context
 -> provider continues without PLAN authority
 -> natural final answer
```

Example product response:

> He actualizado 239 de los 247 contactos. He dejado 8 sin tocar porque no había información suficiente para determinar el país. También he detectado 3 emails duplicados que convendría revisar.

Verification is authoritative context, not automatically the end of the reasoning turn. The post-effect continuation cannot repeat the completed effect.

## 13. Conversation context

Phase 5.6 `ConversationContextManager` is accepted.

Complete Odoo messages/turns remain history authority while the provider receives a bounded derived context containing:

```text
recent raw messages
rolling structured summary
active records/entities/references
previous evidence refs
verified effect refs
conversation/session settings
```

The checkpoint is versioned/immutable per turn and fixes same-conversation ordering hazards by deriving context from causal predecessor turns rather than raw message creation timing.

P5.6 also carries a captured Odoo-language fallback in the bounded session settings. Future deterministic chat/activity text should reuse Odoo translation semantics rather than creating a separate language subsystem.

## 14. Error/recovery behavior

Structured distinctions must survive to the UI:

- provider/account unavailable;
- ACL/policy denied;
- invalid provider/capability output;
- timeout/cancellation;
- safe effect-free retry;
- failed verified effect;
- uncertain/partial post-barrier effect;
- stale/recovery state.

A possible effect is never described as absent merely because provider/browser communication failed.

Future partial-batch UX should preserve counts such as `28 completed / 2 failed` and allow evidence-driven follow-up diagnosis from safe receipts/diagnostic facts rather than raw provider internals.

## 15. Future context, RAG and files

The chat should eventually be able to invoke the same host contracts for:

- JIT installation context;
- Evidence/RAG search;
- logs/source diagnosis;
- file ingestion into Knowledge;
- imports/artifact workflows;
- controlled host operations for Developer profiles;
- web evidence;
- image/file analysis where the provider profile supports it.

The chat does not get a separate tool implementation for those features.

The semantic activity system should describe these families distinctly (`consulting internal knowledge`, `inspecting current Odoo runtime`, `reviewing source/XML`, `searching logs`, `searching the web`, `analyzing image`, etc.) through provider-extensible descriptors rather than frontend hard-codes.

## 16. Additional surfaces

MCP, automations, AI fields and context launchers may reuse the same runtime later. Each surface can have a different effective catalog/policy but cannot maintain an independent authority stack.

Typed Odoo/source references should also be reusable across surfaces so a response can safely link to a permitted record, list/action, view, configuration location, source symbol or external cited URL.

See `PRODUCT_VISION.md`, `CAPABILITY_FRAMEWORK.md`, `research/AGENTIC_PRODUCT_EVOLUTION_PLAYBOOK.md` and `research/P5.8_SEMANTIC_ACTIVITY_UX.md`.

## 17. Target semantic activity and reasoning UX

The next activity UX should distinguish four layers:

```text
private/raw reasoning                 never public
readable provider reasoning summary   optional, bounded, advisory
semantic host work items               normal user-facing progress
technical lifecycle/trace             diagnostic detail
```

### Live compact line

The collapsed line follows the latest meaningful visible step so a user can watch progress without expanding it:

```text
Razonando · Analizando la petición
Razonando · Consultando contactos
Razonando · Buscando "IVA intracomunitario 2026" en agenciatributaria.es
Razonando · Creando presupuestos
```

### Expanded normal view

Default detail is intentionally moderate: major reasoning/work steps plus relevant queries/actions, with equivalent child operations grouped and batch results progressively disclosed.

### Completed view

Completed activity auto-collapses to a discreet summary such as:

```text
Ha pensado durante 32 s · 7 pasos
```

The duration is total turn work time. Very short internal verification/housekeeping can remain in telemetry without appearing as a normal semantic step; initial target visibility threshold is around 1–1.5 seconds and configurable.

### Detail profiles

Presentation should support at least:

```text
compact
normal       # default business user
 detailed
diagnostic  # developer/operator structural details, not private chain-of-thought
```

Normal mode favors human Odoo labels. Technical model/view/capability names can be enabled for developer/operator use.

### References/navigation

Records, models, views, actions, menus/settings and sources should use safe host-resolved typed references rather than model-authored raw URLs. This supports both inline result links and future questions such as `where is setting X?` with a direct Odoo navigation target.

### Internationalization

Every deterministic user-visible phrase must be translatable according to the effective/captured Odoo language. Protocol identity is a stable semantic code plus bounded arguments; localized strings are renderings, not persisted protocol truth.

The complete target contract, external references, settings, generic unknown-model presenter design, batch limits, web/RAG/vision behavior and proposed acceptance gates are in `research/P5.8_SEMANTIC_ACTIVITY_UX.md`.
