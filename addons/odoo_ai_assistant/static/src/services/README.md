# Frontend services

Frontend services hold reusable browser-side state and RPC/live coordination. They keep OWL components from becoming large network/state machines.

## Main service families

| Files | Responsibility |
|---|---|
| `assistant_panel_service.js` | central panel/conversation/turn orchestration |
| `assistant_history_service.js` | native history loading/navigation |
| `assistant_model_service.js` | model-family/model-variant/reasoning preference state |
| `assistant_autonomy_service.js` | autonomy profile state |
| `zz_assistant_auth_service.js` | runtime account/auth UI state |
| `assistant_stream_client.js` | authoritative turn status/event polling |
| `assistant_live_stream_client.js` | independent activity/answer/readable-summary live polling |
| `assistant_panel_streaming_service.js` | binds stream data to panel presentation state |
| `assistant_public_activity_contract.js` | closed browser-safe public activity contract, including bounded contextual references |
| `assistant_semantic_activity.js` | semantic reducer, detail profiles, transient filtering, navigation refs and render bounds |
| `assistant_activity_preferences_service.js` | per-user presentation preferences, including expanded activity height; presentation only, never authority |
| `assistant_reasoning_summary_service.js` | turn-scoped bounded readable reasoning-summary reduction |
| `assistant_public_reference_service.js` | record/model/action/view/menu/setting reference normalization, fresh Odoo revalidation and closed navigation |
| `zzzz_assistant_turn_control_service.js` | active-scope Stop, same-turn correction RPC/idempotency binding, interrupted-answer follow-up and safe reversion request state |
| `assistant_failure_contract.js` | safe structured failure contract |
| `screen_context_service.js` | captures bounded current Odoo screen context |
| `zzz_assistant_turn_scope_service.js` | per-conversation/background execution scopes |

## State/authority rules

### 1. Scope async callbacks to the owning turn/conversation

A late result from Chat A must update Chat A, not whichever chat is visible when the callback arrives. This applies equally to Stop, corrections, semantic activity, provisional answer text and readable reasoning summaries.

### 2. Server state wins

Browser state optimizes UX. Odoo owns turn status, intervention acceptance/order, ACLs, approval, final history, typed-reference authorization, reversion availability and effect certainty.

### 3. Provisional presentation is not authority

Answer deltas, semantic progress, navigation chips and readable reasoning summaries improve responsiveness but cannot authorize tools/effects or override the final persisted answer.

### 4. Private reasoning never enters browser state

Only the provider-declared readable summary channel is accepted. Raw/private reasoning deltas are intentionally ignored before the public live seam.

### 5. Turn correction is not a second ordinary turn

While the active scope is processing, text submission goes to `/odoo_ai/v1/turn/redirect` using that scope's durable Odoo turn ID and a `client_intervention_id`. The draft is cleared only after Odoo confirms the durable intervention. Empty composer + processing calls `/odoo_ai/v1/turn/cancel` for the same scope.

Provider thread/turn IDs are never browser state.

### 6. Navigation is typed and revalidated

The browser never executes arbitrary model-generated Odoo routes. `assistant_public_reference_service.js` accepts only closed typed references:

```text
odoo_record
odoo_model
odoo_action
odoo_view
odoo_menu
odoo_setting
```

Immediately before every open, the browser sends only the closed reference identity to `/odoo_ai/v1/public-references`. Odoo revalidates current permissions/existence/visibility and returns a second closed descriptor. Only that descriptor is converted to an `actionService` call.

### 7. Reversion is host-declared and confirmed

The frontend shows `Revertir cambios` only when the server response says compensation is available. It asks for explicit confirmation and never constructs an inverse business operation itself. Odoo executes/verifies the host-only compensator.

## P5.8 presentation/control behavior

P5.8 adds compact/normal/detailed/diagnostic semantic activity plus current-turn interaction:

```text
idle + text              -> Enviar mensaje
processing + empty       -> Detener respuesta
processing + text        -> Corregir instrucción
```

The textarea remains editable during normal processing. Stop/correction remain isolated to the active conversation scope. Partial stopped prose is retained as `Interrumpido`.

Navigation references can render in streaming activity and as structured chips below the final answer. Revoked references show a discreet unavailable notice and do not reach `actionService`.

The implementation remains validation-pending until `docs/research/EXECUTION_STATE.md` records the required P5.8 validation chain as accepted.

Task-plan presentation suppresses ordinary one-step plans because they add latency-shaped noise to
simple interactions. A blocked one-step plan and an explicit replan remain visible because both carry
useful recovery information.

## Adding a service

A frontend service should have a narrow responsibility and a corresponding HOOT test when state transitions matter.

Do not:

- cache permissions as permanent authority;
- hide server-side `recovery_required`/uncertain effect states;
- cancel another conversation merely because the user navigated away;
- create a second ordinary turn for an in-flight correction;
- put provider IDs/secrets/raw responses/private reasoning into browser storage;
- construct arbitrary Odoo actions/URLs from model text;
- implement compensation logic in JavaScript.

A new channel/surface should reuse server contracts and equivalent scoped state rather than clone the agent runtime.
