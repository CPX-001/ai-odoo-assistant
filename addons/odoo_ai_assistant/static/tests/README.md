# Frontend HOOT tests

These tests exercise the Assistant's Odoo web-client contracts without treating JavaScript state as server authority.

They cover panel behavior, composer/docking, history, auth/model/autonomy services, streaming/live clients, semantic activity, failures, markdown, screen context, conversation turn scopes, current-turn controls and contextual navigation.

## High-value invariants

Frontend tests should prove that:

- a late callback updates the turn/conversation that owns it;
- switching chats does not cancel or overwrite unrelated background work;
- public activity, provisional answer and readable-summary channels remain separate;
- a submitted turn shows request analysis immediately, and only the latest semantic step remains
  visually active while earlier steps settle in sequence;
- a fresh authenticated Assistant entry opens on history rather than an empty chat;
- final state reconciles provisional UI state;
- model/autonomy controls do not mutate settings already captured by a queued/running turn;
- idle+text is Send, processing+empty is Stop and processing+text is Correct instruction;
- the textarea stays editable while ordinary processing runs;
- Stop/correction use only the active conversation scope's durable Odoo turn ID;
- the Stop control exposes `Detener respuesta` through title/aria-label semantics;
- same-turn redirect responses are bound to the expected `client_intervention_id`;
- interrupted provisional text remains visible as interrupted content;
- record/model/action/view/menu/setting references are closed typed values;
- streaming and final references never execute model-authored routes;
- every open revalidates through Odoo before `actionService`;
- a revoked reference does not reach `actionService`;
- settings sharing one settings action still have distinct presentation identities;
- safe failure/effect/reversion-state semantics survive presentation;
- browser rendering does not expose raw private/provider content or provider thread/turn IDs.

## P5.8 focused files

High-value focused coverage includes:

```text
assistant_turn_control.test.js
assistant_public_reference_service.test.js
assistant_navigation_references.test.js
assistant_semantic_activity.test.js
assistant_semantic_navigation.test.js
assistant_live_stream_client.test.js
assistant_reasoning_summary_service.test.js
assistant_turn_scope_service.test.js
```

These tests being present in the repository is not a PASS result. The complete `@odoo_ai_assistant` HOOT suite must be run in the accepted Odoo 18 browser-test environment and the result recorded against the exact candidate SHA.

## Running

Odoo 18 discovers `.test.js` files under the addon's `static/tests` bundle. The interactive runner is `/web/tests`; use the existing headless/filtered P5 runner when available to execute the complete `@odoo_ai_assistant` suite.

See `docs/research/P5.8_VALIDATION_RUNBOOK.md` for the current acceptance chain and real browser gates.

## Adding a test

Prefer testing user-visible/state-machine and authority-boundary behavior over incidental implementation details. Mock the server boundary only as much as needed to make ownership, ordering and error behavior deterministic.
