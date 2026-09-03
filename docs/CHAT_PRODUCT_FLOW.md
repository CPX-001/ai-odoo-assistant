# Chat product flow

This document describes the current embedded chat path and product-level invariants. It supersedes the retired browser/Odoo/Assistant-Service flow.

## 1. Current end-to-end path

```text
OWL Assistant panel
    |
    | authenticated Odoo JSON/RPC only
    v
Odoo controllers/services
    |
    +--> conversation/message persistence
    +--> screen-context validation
    +--> account/model/reasoning/planning/policy settings snapshot
    v
odoo.ai.turn (queued)
    |
    v
native ir.cron + lease claim
    |
    v
AgentTurnService / host loop
    |
    +--> immutable planning strategy
    +--> effective CapabilityRegistry
    +--> provider-neutral NextDecision (Codex today)
    +--> optional explicit TaskPlan / host capability execution
    +--> semantic live events / answer deltas
    v
EffectPlan prepare / approval / recovery-unit execute / verify
    |
    +--> authoritative turn result
    +--> EffectJournal / recovery state
    +--> structured navigation references
    v
OWL observes Odoo status + live cursor
```

The browser never calls Codex directly and never owns provider credentials, provider turn/thread IDs or capability authority.

## 2. Submit is short and durable

Submitting a new ordinary message remains a short Odoo request:

1. validate caller/message/screen hint;
2. locate/create owned conversation;
3. persist user message;
4. snapshot turn-relevant model/reasoning/planning/policy/company/context settings;
5. create durable queued `odoo.ai.turn`;
6. trigger available native runner slots;
7. return durable turn/conversation identity and state.

Reasoning/provider work continues outside the submit request. Browser navigation, panel close or polling failure does not cancel the server turn.

## 3. Processing concurrency

The backend queue uses leases and `FOR UPDATE SKIP LOCKED`. P5.2 accepted bounded two-slot scheduling with same-conversation causal ordering, cross-conversation concurrency, backpressure and fairness.

Frontend state is scoped per conversation/turn, not one global loading lock. While Chat A runs, the user can switch to Chat B/C, navigate Odoo and change next-turn preferences. The running turn continues independently.

The capacity value remains configurable product/runtime policy rather than a permanent architectural constant.

## 4. One causal turn per conversation plus same-turn intervention

A second **ordinary** message must not race an unresolved turn in the same conversation. Causal turn ordering remains one active ordinary turn per conversation.

P5.8 adds a different operation: an **intervention/correction of the current turn**.

```text
ordinary new request       -> new odoo.ai.turn when conversation is free
correction while active    -> durable intervention on the SAME odoo.ai.turn
Stop                       -> cancel only the SAME active odoo.ai.turn
```

This is not conversation branching and is not navigation.

## 5. Interactive composer behavior

Current composer contract:

```text
idle + empty draft              -> disabled
idle + text                     -> Enviar mensaje
processing + empty draft        -> Detener respuesta
processing + text               -> Corregir instrucción
awaiting approval + text        -> Corregir instrucción
```

The textarea remains editable while normal reasoning is processing. The Stop control uses a square icon and accessible title/aria-label `Detener respuesta`.

The draft for a correction is cleared only after Odoo confirms durable acceptance.

## 6. Durable interventions

Corrections are persisted in `odoo.ai.turn.intervention` before the provider is asked to react.

Each row is bounded and bound to:

```text
turn
conversation
user
company
sequence
client_intervention_id
message
state
```

Multiple corrections preserve monotonic order. Duplicate client IDs cannot create duplicate intervention/message rows; conflicting reuse fails closed. Count and aggregate byte budgets prevent unbounded intervention growth.

### Queued turn

Corrections remain on the same queued turn and are included before its first provider decision.

### Running turn

The host observes the durable correction. If the disposable Codex App Server subturn is alive, the host may send `turn/steer` with `expectedTurnId` to make the correction responsive. If steering is unavailable or no subturn is alive, the host interrupts/discards the ephemeral provider work and restarts the next `NextDecision` from Odoo's durable intervention state.

Codex state is therefore never the only copy of the user correction.

### Awaiting approval

A later user correction explicitly supersedes the pending plan:

```text
approval.rejected
 -> old executable plan cleared
 -> same durable turn requeued/resumed
 -> new intervention becomes current instruction
```

The prior plan cannot execute after it has been superseded.

## 7. Stop and interrupted answers

Stop is scoped to the current conversation's durable Odoo turn UUID. Another running conversation is unaffected.

Odoo records `cancel_requested`/`cancelled`; a live provider subturn receives best-effort `turn/interrupt`. Provider IDs remain host-internal.

Provisional answer text already shown to the user is retained as an Assistant message and marked:

```text
— Interrumpido
```

An accepted Stop prevents a stale later final response from becoming authoritative.

Stop after an effect checkpoint is not a rollback. Already verified durable effects remain visible as completed actions and only remaining reasoning/work can stop. A later recovery unit rechecks Stop/redirect before it can start.

## 8. TaskPlan, effect ordering, approval and verification

Natural-language intent is never direct authorization.

A TaskPlan is public progress only:

```text
goal
revision / revision_kind / revision_summary
bounded steps with title/state/dependencies
```

It cannot contain executable capability arguments or approval authority. Visible planning has two current product modes:

```text
Directo (adaptive)  default; a new turn cannot create a TaskPlan
Plan (deliberate)   explicit user opt-in; initial TaskPlan required before capability/effect work
```

Directo may still answer, inspect schema, perform multiple bounded reads, reason over evidence and stage several typed EffectPlan steps. The number of tool calls, effect proposals or structural complexity signals never promotes a Direct turn into a visible TaskPlan. A short chain such as “find Demo; create it if absent; create a test quotation” therefore stays planless unless Plan was selected.

The former `auto` selector is legacy compatibility only and is no longer exposed/accepted for new preferences. Stored legacy `auto` preferences normalize to Direct; historical immutable snapshots remain readable.

A structural replan is possible only for an existing TaskPlan, requires new host-observed evidence, and the host supplies the exact legal next revision.

Effectful work uses a separate bounded typed EffectPlan:

```text
model proposes typed step(s), one NextDecision at a time
 -> host validates each CapabilityDefinition + arguments
 -> accumulate ordered EffectPlan (max 5)
 -> prepare/preview/preconditions for every step
 -> current policy
 -> approval if required
 -> revalidate version/binding/preconditions
 -> final turn-control check for the recovery unit
 -> durable checkpoint / write barrier
 -> execute as effective user
 -> verify each step
 -> authoritative receipt + EffectJournal / recovery state
```

The race with Stop/correction is serialized host-side. Valid outcomes are control-before-effect or effect-before-late-control; not “accepted correction plus stale plan effect”.

Recovery-unit mode is trusted host/capability metadata, not model text:

```text
odoo_atomic  Odoo-local steps sharing one transactional recovery unit
segmented    durable internal unit boundary before a later unit
external     non-transactional/external unit whose interrupted outcome may be uncertain
```

A persisted in-flight unit is never blindly replayed.

For one Odoo-local atomic unit, a capability rejection after the write barrier is recoverable only when the host rolls
back the transaction and every durable journal row proves `rolled_back`. The host then appends a sanitized
`plan_execution_error` and lets the model narrow or correct the complete plan within the original intent. That repair
does not create new approval authority: the original approval is reused only for the same operation over a strict or
equal subset of its approved record identities. Expanding the scope, changing capability/model/operation, an
unproven rollback, or an external/uncertain effect stops automatic repair and follows the normal approval/recovery
path.

Preparation and preflight failures cross no write barrier. They are also returned to the same bounded decision loop
as structured evidence (`code`, phase, capability and sanitized details), so the model may inspect effective schema,
visible records, Knowledge or installed-source Evidence and propose a corrected plan. A raw Python traceback is never
provider or browser context. Capability failures during read/reasoning follow the same pattern; authority, policy and
access denials remain terminal for further capability use, but the provider still gets one opportunity to explain the
business reason naturally. If bounded correction budgets are exhausted, the host closes the turn with a safe natural
fallback and discards incomplete effect proposals rather than presenting a protocol error as the answer.

Completed effect checkpoints retain bounded exact resource references (`model` plus produced record identities).
This lets later turns resolve ordinary follow-ups such as “elimínalos” or “todos los que creaste” without forcing the
user to repeat technical identifiers. The target is always revalidated under current ACLs, record rules and preview.
For contact deletion, both the current bulk capability and its legacy bounded route exclude active-user and company
partners host-side, show those exclusions in the approval preview, and verify only the eligible deletion scope.

## 9. Safe compensation and recent effect journal

P5.8 adds explicit host-side compensation for selected verified reversible operations. It is not a PostgreSQL transaction rollback.

Initial families:

```text
odoo.record.patch
odoo.record.archive
odoo.record.unarchive
```

After a successful verified effect, the host can declare compensation `available`. The UI lists performed actions and offers `Revertir cambios` only when a matching HOST-only compensator exists. The user must confirm.

Before restoring state, Odoo revalidates current write permission/record rules and verifies the record still matches the previously verified post-effect state. A later modification by another user causes a conflict and is not overwritten. Only after the inverse write is re-read and verified does the UI report `Cambios revertidos`.

Phase 6 adds a short-lived Odoo-owned EffectJournal with bounded recovery/inspection evidence and classification. It is not a backup or general audit warehouse. Supported compensation marks matching reversible journal rows reverted after verification.

## 10. Semantic public activity and live TaskPlan

P3 browser-safe live persistence remains the transport/durability base. P5.8 reduces trusted lifecycle events into semantic work items correlated by host-generated `activity_id`.

The UI distinguishes:

```text
private/raw reasoning                 never public
readable provider reasoning summary   optional, bounded, advisory
TaskPlan                              explicit bounded public planning/progress
semantic host work items              normal user-facing progress
technical lifecycle/trace             diagnostic detail
```

A compact live line follows the latest meaningful step. A direct model answer creates no generic Thought activity; public work begins only after the host accepts a capability, effect or explicit TaskPlan decision. Completed activity collapses to total elapsed time plus semantic step count. Normal/compact history replaces provider retry failures with one terminal failure, while detailed and diagnostic profiles retain the underlying events. Technical identifiers are hidden by default.

Readable provider summaries accept bounded `summaryTextDelta`; raw reasoning `textDelta` never enters public state.

Activity belongs to the Assistant answer that it explains. Odoo persists the public semantic activity and bounded
readable summaries with that historical message, so leaving the panel, reloading or opening the conversation later
does not remove it. While a turn runs there is exactly one live disclosure for that conversation; once the final
answer is reconciled it becomes the historical disclosure above that answer and closes by default. The closed caret
points right (`>`); opening it rotates the same caret and reveals a scrollable detail area whose visible line count
comes from the activity presentation setting (five by default).

The normal surface deliberately avoids a spinner, nested Assistant cards and provider-authored Markdown planning
headings. Only the current semantic text receives the subtle wave animation. Isolated raw headings such as
`**Planning model discovery**` are presentation noise and are not rendered as public reasoning.

Running status separately projects the latest validated TaskPlan when Plan mode is in use. The UI chooses the newest valid revision and prefers the authoritative final response on equal revisions, so a stale final live poll cannot hide the terminal plan.

## 11. Answer streaming

Structured provisional answer streaming remains separate from activity.

Conceptual browser channels/surfaces are:

```text
activity.event
optional TaskPlan status projection
answer.delta
reasoning.summary.delta
turn.final
turn.failure
```

Provisional prose is not authority. The final validated Odoo turn result reconciles it. After verified effects, the host may allow read-only post-effect reasoning so the provider synthesizes the natural final answer without receiving another PLAN opportunity.

## 12. Contextual navigation is a separate contract

Turn correction changes what the active Assistant turn should do. Contextual navigation merely gives the user a validated place to open in Odoo. They are intentionally separate.

Current first-class public reference kinds:

```text
odoo_record
odoo_model
odoo_action
odoo_view
odoo_menu
odoo_setting
```

For records/models, existing grounded result identities remain supported.

For contextual UI discovery, the read-only capability `odoo.resolve_navigation` accepts only semantic query text plus bounded kind/limit hints. Odoo resolves candidate models, window actions, safe views, currently visible menus and installed `res.config.settings` options under the effective user with `su=False`.

The model does **not** provide authoritative Odoo IDs or routes.

## 13. Fresh navigation revalidation

Every clicked reference is returned to Odoo before navigation:

```text
browser typed reference
 -> /odoo_ai/v1/public-references
 -> exact closed shape validation
 -> current user/company/access/group/menu/schema checks
 -> closed navigation descriptor
 -> OWL actionService
```

A model-authored raw URL/route never reaches `actionService` as authority.

A revoked/deleted reference returns unavailable, shows a discreet notice and does not navigate.

## 14. Streaming and final-answer references

Navigation results may be shown as compact chips inside semantic activity while the turn runs.

The host also captures validated `odoo.resolve_navigation` results into bounded turn state. Final turn responses carry a structured `references` collection separately from prose, rendered below the answer area.

This allows natural responses such as:

> Puedes encontrar esta opción aquí.

while the actual clickable destination is a typed Odoo reference resolved/revalidated by the host, not a Markdown `/web#...` URL generated by the model.

## 15. Progressive disclosure

Large record result sets remain a presentation concern rather than an execution limit:

```text
first page: 5 rows by default
show more: bounded next page
show remaining: only inside hard render ceiling
over limit: model/list navigation fallback
```

The same design keeps streaming activity compact while preserving access to useful grounded records.

## 16. Settings while a turn runs

Turn-sensitive execution settings remain snapshots. A turn queued with model/reasoning/planning/policy X continues with X even if the user changes selectors for future turns.

Presentation preferences may change display without changing current turn authority.

Approval/rejection and same-turn intervention are explicit control transitions, not ordinary preference edits.

## 17. Conversation context

P5.6 `ConversationContextManager` remains accepted. Complete Odoo messages/turns are history authority; provider context is a bounded derived view containing recent causal messages, rolling summary, entities/references, evidence/verified-effect refs and session settings.

Intervention messages are stored in chat history but excluded from duplicated ordinary-history projection when they are already supplied as explicit current-turn intervention context.

Opening the Assistant normally enters conversation history. A conversation may open directly only when the current
browser session already has an active conversation to resume; a terminal turn is never restored as the active turn.

## 18. Error/recovery behavior

Structured distinctions remain visible:

- provider/account unavailable;
- ACL/policy denied;
- invalid provider/capability output;
- timeout/cancellation;
- safe effect-free retry;
- failed verified effect;
- transactional rollback vs uncertain external in-flight effect;
- completed segmented unit vs later failed/unexecuted unit;
- stale/recovery state;
- intervention conflict/limit/budget;
- navigation reference unavailable;
- compensation unavailable/conflicted/unauthorized.

A possible effect is never described as absent merely because provider/browser communication failed.

## 19. Future context, RAG, files and surfaces

The chat should eventually invoke the same host contracts for JIT installation context, Evidence/RAG, source/XML/log diagnosis, company knowledge/files, artifact/import workflows, controlled technical operations, web evidence and multimodal analysis where supported.

MCP, automations, AI fields and launchers may reuse the same capabilities later with different effective catalogs/policies, but not independent authority stacks.

Future reference kinds may include source/document/web evidence only when those entities can be grounded and revalidated safely.

RAG/JIT context is an optimization for discovery and grounding, not execution authority. A future Odoo knowledge
provider may retrieve likely models, fields, views, domains and company documentation under the current ACL/company
scope, with provenance, freshness and cache identity. This can remove repeated schema-search calls and shorten the
reasoning prompt. It cannot approve an effect, bypass live validation, or replace a `CapabilityDefinition` handler.

See `PRODUCT_VISION.md`, `CAPABILITY_FRAMEWORK.md`, `research/AGENTIC_PRODUCT_EVOLUTION_PLAYBOOK.md`, `research/P5.8_IMPLEMENTATION.md`, `research/P6_PLANNING_EFFECTPLAN_IMPLEMENTATION.md`, `research/P6_EFFECT_RECOVERY_JOURNAL_IMPLEMENTATION.md`, `research/P6_ADAPTIVE_PLANNING_IMPLEMENTATION.md` and `research/PERIODIC_FULL_REGRESSION_RUNBOOK.md`.
