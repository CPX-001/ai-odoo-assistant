# Frontend services

Frontend services hold reusable browser-side state and RPC/live coordination. They keep OWL components from becoming large network/state machines.

## Main service families

| Files | Responsibility |
|---|---|
| `assistant_panel_service.js` | central panel/conversation/turn orchestration |
| `assistant_history_service.js` | native history loading/navigation |
| `assistant_model_service.js` | model preference state |
| `assistant_autonomy_service.js` | autonomy profile state |
| `zz_assistant_auth_service.js` | runtime account/auth UI state |
| `assistant_stream_client.js` | authoritative turn status/event polling |
| `assistant_live_stream_client.js` | public live event/delta polling |
| `assistant_panel_streaming_service.js` | binds stream data to panel presentation state |
| `assistant_public_activity_contract.js` | browser-safe public activity contract |
| `assistant_failure_contract.js` | safe structured failure contract |
| `screen_context_service.js` | captures bounded current Odoo screen context |
| `zzz_assistant_turn_scope_service.js` | P5.1 per-conversation/background execution scopes |

## Three state rules

### 1. Scope async callbacks to the owning turn/conversation

A late result from Chat A must update Chat A, not whichever chat is visible when the callback arrives.

### 2. Server state wins

Browser state optimizes UX. Odoo still owns turn status, approval state, final history and effect certainty.

### 3. Provisional text is provisional

Answer deltas improve responsiveness but are reconciled with the final persisted answer.

## P5.1 note

`zzz_assistant_turn_scope_service.js` is implemented in `main` to remove the single global panel execution scope. Required P5.1 deterministic/real validation is still open, so do not treat this implementation as accepted foundation until `docs/research/EXECUTION_STATE.md` says so.

## Adding a service

A frontend service should have a narrow responsibility and a corresponding HOOT test when state transitions matter.

Do not:

- cache permissions as permanent authority;
- hide server-side `recovery_required`/uncertain effect states;
- cancel another conversation merely because the user navigated away;
- put provider-specific secrets or raw responses into browser storage.

A new channel/surface should reuse server contracts and equivalent scoped state rather than clone the agent runtime.
