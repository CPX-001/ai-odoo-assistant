# Chat product flow

This document describes the current embedded chat path. It supersedes the former browser/Odoo/Assistant-Service HTTP flow.

## Current flow

```text
OWL Assistant panel
    |
    | Odoo RPC
    v
Odoo controllers/services
    |
    +--> conversation/message persistence
    +--> screen context validation
    +--> account/policy checks
    |
    v
odoo.ai.turn (queued)
    |
    v
ir.cron claims turn with lease
    |
    v
AgentTurnService
    |
    +--> effective CapabilityRegistry views
    +--> ReasoningEngine -> Codex App Server subprocess
    |
    v
host validation / policy / approval / execution / verification
    |
    v
turn result + sanitized events persisted in Odoo
    |
    v
OWL polls Odoo and renders progress/result
```

The browser never calls a separate Assistant Service. There is no current `/assistant/chat/turns` sidecar API, shared browser-side machine secret, or Assistant PostgreSQL transcript store.

## Opening the Assistant

The frontend first resolves the database-scoped Codex account state. Chat/history bootstrap is gated until the runtime account is usable. Account polling only runs while the Assistant is open and the page is visible.

Once usable, the panel loads Odoo-owned conversation state and may submit new messages with current screen context. Screen context is a navigation/context hint; the server reconstructs identity, companies and permissions independently.

## Submit

Submitting a message should remain a short Odoo request:

1. validate caller and input;
2. persist user message/conversation state;
3. create a durable `odoo.ai.turn` with the relevant context/policy snapshot;
4. schedule/wake native cron processing;
5. return the turn identifier/state to the browser.

Long reasoning or provider execution does not need to remain inside the browser HTTP request.

## Processing

A cron worker claims the turn with a bounded lease. `AgentTurnService` rebuilds the effective Odoo user/company context and effective capability catalog, invokes the reasoning engine and handles capability calls through host-owned validation/execution.

The model can request only capabilities visible in the effective reasoning/planning view. Naming a capability does not create access. Reads and writes continue to obey Odoo permissions and capability bounds.

## Effects and approval

Effectful requests do not become authorized because the user/model mentioned an action in chat. The current host path uses capability effect/risk metadata plus configured policy and approval semantics.

The intended product UX is:

```text
prepare/preview -> policy -> approval if required -> execute -> verify -> receipt/result
```

An approval must bind to the prepared action/preconditions. If the host cannot confirm whether an effect happened, the turn should surface recovery/uncertain state rather than invite a blind retry.

## Polling and progress

The browser polls Odoo-owned turn/event state. Persisted events are sanitized public progress projections, not provider chain-of-thought. They may describe categories of work or approval/verification state but must not expose raw prompts, sensitive arguments, credentials or private reasoning.

At the current audited baseline, completed and approval-waiting turn status includes the persisted authoritative result payload as the browser `response`.

For Foundation Stabilization Phase 0 measurement, `streamAssistantChat()` also accepts optional diagnostic-only `onTiming` and `nowCall` hooks. The normal product caller does not need to provide them. The client records monotonic checkpoints for `submit_received`, `turn_persisted`, `browser_first_activity` and `browser_final`.

The Codex adapter also emits content-free `diagnostic.timing` events for runtime/provider lifecycle checkpoints (`runtime_started`, process start, initialize, thread/turn start, first provider event and first provider answer delta). Their payload is limited to checkpoint name plus process-local elapsed milliseconds. The answer delta text itself is neither persisted nor forwarded by this instrumentation. These measurement hooks do not change the polling transport and do **not** imply real assistant answer streaming; `browser_first_answer_delta` remains unavailable until the later streaming phase is implemented.

## Conversation persistence

Conversation, message, turn and public event persistence is Odoo-native. Codex threads/process state are not the product memory authority.

## Error behavior

Useful distinctions should survive to the product layer when known: account/provider unavailable, capability denied, ACL denial, invalid provider output, timeout, cancellation, failed verified effect, uncertain/partial effect and stale-turn recovery. A generic assistant error is only the fallback when no safer specific state exists.

## Future surfaces

Context launchers, automations, AI fields or MCP can reuse this host/runtime later, but should not create parallel authorization or tool registries. The chat is one invocation surface over the same Odoo authority model.
