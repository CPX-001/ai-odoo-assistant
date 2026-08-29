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
| `assistant_public_activity_contract.js` | closed browser-safe public activity contract |
| `assistant_semantic_activity.js` | P5.8 semantic reducer, detail profiles, transient filtering and render bounds |
| `assistant_activity_preferences_service.js` | per-user P5.8 presentation preferences; presentation only, never authority |
| `assistant_reasoning_summary_service.js` | turn-scoped bounded readable reasoning-summary reduction |
| `assistant_public_reference_service.js` | typed Odoo record/model resolution, fresh host revalidation and safe navigation |
| `assistant_failure_contract.js` | safe structured failure contract |
| `screen_context_service.js` | captures bounded current Odoo screen context |
| `zzz_assistant_turn_scope_service.js` | per-conversation/background execution scopes |

## State/authority rules

### 1. Scope async callbacks to the owning turn/conversation

A late result from Chat A must update Chat A, not whichever chat is visible when the callback arrives. This applies equally to semantic activity, provisional answer text and readable reasoning summaries.

### 2. Server state wins

Browser state optimizes UX. Odoo owns turn status, ACLs, approval, final history, typed-reference authorization and effect certainty.

### 3. Provisional presentation is not authority

Answer deltas, semantic progress and readable reasoning summaries improve responsiveness but cannot authorize tools/effects or override the final persisted answer.

### 4. Private reasoning never enters browser state

Only the provider-declared readable summary channel is accepted. Raw/private reasoning deltas are intentionally ignored before the public live seam.

### 5. Navigation is typed and revalidated

The browser never executes arbitrary model-generated Odoo routes. `assistant_public_reference_service.js` sends a closed record/model descriptor back to Odoo immediately before navigation; the host revalidates current access and returns only a bounded form/list descriptor.

## P5.8 presentation behavior

P5.8 adds compact/normal/detailed/diagnostic semantic activity projections without changing the underlying P3 durable/live facts. Default normal mode groups correlated lifecycle rows, hides low-value transient verification, keeps failures/approval visible and uses a five-row progressive disclosure page.

The implementation is present but remains validation-pending until `docs/research/EXECUTION_STATE.md` records the required P5.8 gates as accepted.

## Adding a service

A frontend service should have a narrow responsibility and a corresponding HOOT test when state transitions matter.

Do not:

- cache permissions as permanent authority;
- hide server-side `recovery_required`/uncertain effect states;
- cancel another conversation merely because the user navigated away;
- put provider-specific secrets/raw responses/private reasoning into browser storage;
- construct arbitrary Odoo actions from model text.

A new channel/surface should reuse server contracts and equivalent scoped state rather than clone the agent runtime.
