# Frontend HOOT tests

These tests exercise the Assistant's Odoo web-client contracts without treating JavaScript state as server authority.

They cover areas such as panel behavior, composer/docking, history, auth/model/autonomy services, streaming/live clients, failures, markdown, screen context and P5.1 turn scopes.

## High-value invariants

Frontend tests should prove that:

- a late callback updates the turn/conversation that owns it;
- switching chats does not cancel or overwrite unrelated background work;
- public activity and provisional answer channels remain separate;
- final state reconciles provisional UI state;
- safe failure/effect-state semantics survive presentation;
- model/autonomy controls do not mutate settings already captured by a queued/running turn;
- browser rendering does not expose raw private/provider content.

## P5.1 gate

`assistant_turn_scope_service.test.js` is the focused deterministic test for per-conversation execution scopes. Passing this test alone is not the full acceptance condition; `docs/research/EXECUTION_STATE.md` also requires affected P2-P4 regressions and real browser scenarios.

## Adding a test

Prefer testing user-visible/state-machine behavior over implementation details. Mock the server boundary only as much as needed to make ownership, ordering and error behavior deterministic.
