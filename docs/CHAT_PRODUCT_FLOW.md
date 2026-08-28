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

Submitting a message should remain a short Odoo request:

1. validate caller/message/screen hint;
2. locate/create owned conversation;
3. persist user message;
4. snapshot turn-relevant model/policy/company/context settings;
5. create durable queued `odoo.ai.turn`;
6. trigger available native runner slots;
7. return turn/conversation id and state.

Reasoning/provider work continues outside the submit request.

This means browser navigation, closing the panel or a temporary polling failure must not cancel the server turn.

## 3. Current processing concurrency

The current backend queue claims work with `FOR UPDATE SKIP LOCKED`, leases and stale recovery. Two cron records currently provide two bounded runner slots.

This permits separate turns to be claimed concurrently at the backend, subject to actual Odoo cron/process capacity.

However, the current browser still has a panel-global `state.loading` concept. While the visible turn runs, it currently disables important controls including the composer, conversation selector and model/autonomy pickers.

Therefore current backend concurrency capability and current frontend multitasking capability are **not equivalent**.

## 4. Target non-blocking chat behavior

Phase 5 changes execution ownership from `panel is loading` to `turn/conversation has running work`.

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

The history/conversation list should expose background state so the user can see which chats are queued/running/awaiting approval/failed/recovery/completed.

## 5. Initial concurrency semantics

### Across conversations

Multiple conversations may have active turns concurrently up to host/provider capacity.

### Inside one conversation

Initial target: one active **causal** turn at a time.

A second ordinary message in the same conversation must not race against an unresolved first turn and build context from a different future. It may be queued behind it or the UI may require explicit steering semantics later.

Future `steer current turn` or conversation branching is separate product work and requires explicit contracts/tests.

## 6. Capacity and backpressure

Concurrency must become configurable/observable rather than assuming two slots forever.

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

OCA `queue_job` is a useful reference for channels/capacity/background recovery, but current native queue semantics are retained unless an ADR/evaluation justifies a dependency/replacement.

## 7. Settings while a turn is running

Turn-sensitive settings are snapshots, not live mutable references.

For example current enqueue already stores the selected reasoning model and policy payload. The target applies the same rule to future technical profile/strategy/config versions.

Therefore:

```text
Turn A queued with model X + Balanced
user changes UI to model Y + Autonomous
Turn A continues with X + Balanced
future Turn B uses Y + Autonomous
```

The user is free to open/change those selectors while A runs.

Approval/rejection is not a normal setting edit; it is an explicit transition bound to A's prepared effect and may resume A.

## 8. Public activity

Current `main` includes an independent public activity store/projection pending formal P3 acceptance.

Public activity is trusted host projection such as:

```text
Consultando res.partner
Leyendo esquema de sale.order
Preparando cambio
Esperando aprobación
Ejecutando
Verificando
```

It is not private provider reasoning and must not expose prompts, raw arguments/results, credentials, stdout/stderr or chain-of-thought.

The independent live-event cursor is intentionally separate from the worker business transaction so progress can become visible before final commit without committing business effects early.

## 9. Answer streaming

Current `main` includes the P4 answer projection pending formal acceptance.

Codex `item/agentMessage/delta` is parsed to expose only the structured `final_answer.answer` text. Provisional output is not authority.

Browser channels are conceptually:

```text
activity.event
answer.delta
turn.final
turn.failure
```

The final validated turn result remains authoritative and reconciles provisional answer text.

## 10. Background turn observation

The browser may detach from a turn and later resume from Odoo state.

Target frontend state is keyed by turn/conversation rather than one global stream buffer.

The visible chat should consume live updates at normal cadence. Background chats may use lighter periodic refresh/badges to avoid multiplying polling cost indefinitely.

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

Current implementation supports one canonical effect step. The future product supports bounded multi-step `EffectPlan` while retaining the same host controls.

## 12. Post-effect conversation

Current implementation still finishes successful action execution with a host-produced completion answer.

Target behavior is:

```text
verify effect
 -> add verified receipt to private working context
 -> provider continues reasoning
 -> provider produces natural final answer
```

Example target response:

> He actualizado 239 de los 247 contactos. He dejado 8 sin tocar porque no había información suficiente para determinar el país. También he detectado 3 emails duplicados que convendría revisar.

Verification is authoritative context, not automatically the end of the reasoning turn.

## 13. Conversation context

Messages are fully Odoo-persisted, but current reasoning context is intentionally bounded and currently relies heavily on recent message composition.

Target `ConversationContextManager` maintains:

```text
recent raw messages
rolling structured summary
active records/entities/references
previous evidence refs
verified effect refs
conversation-scoped settings
```

This supports natural follow-ups without making Codex threads the persistence authority.

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

## 15. Future context, RAG and files

The chat should eventually be able to invoke the same host contracts for:

- JIT installation context;
- Evidence/RAG search;
- logs/source diagnosis;
- file ingestion into Knowledge;
- imports/artifact workflows;
- controlled host operations for Developer profiles;
- web evidence.

The chat does not get a separate tool implementation for those features.

## 16. Additional surfaces

MCP, automations, AI fields and context launchers may reuse the same runtime later. Each surface can have a different effective catalog/policy but cannot maintain an independent authority stack.

See `PRODUCT_VISION.md`, `CAPABILITY_FRAMEWORK.md` and `research/AGENTIC_PRODUCT_EVOLUTION_PLAYBOOK.md`.
