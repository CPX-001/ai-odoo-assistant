# E2E tests

The scripts in this directory were created for earlier sidecar/delegation milestones and are retained mainly as historical/regression evidence. Their old service URL, machine-secret, Assistant DB or standalone API assumptions are **not** current product requirements.

## Current embedded-product E2E target

New/current E2E coverage should exercise the Odoo addon as the product boundary:

```text
browser/Odoo RPC
 -> conversation + durable turn
 -> Odoo cron worker
 -> AgentTurnService / effective capabilities
 -> Codex adapter
 -> host policy/approval/execution/verification
 -> persisted result/events
 -> browser UI
```

Important scenarios include:

- fresh database account disabled/gated;
- administrator device-code connect/cancel/logout;
- normal authenticated chat turn;
- account/provider unavailable;
- effective-user ACL/record-rule/field-access/multi-company behavior;
- schema-first query bounds;
- effect preview/approval/verification;
- stale approval/precondition or ambiguous effect recovery;
- cancellation and Odoo restart/stale-lease recovery;
- sanitized progress/diagnostics with no secrets or chain-of-thought;
- prompt injection/untrusted record/document text when relevant.

## Legacy scripts

Existing sidecar-era helper scripts may still be run when validating preserved legacy code or when a current migration deliberately reuses one of their contracts. Passing them does not prove the embedded runtime works; failing them after an intentional retirement does not by itself indicate a current-product regression.

For current test priorities see `../AGENTS.md` and root `docs/CURRENT_STATE.md`.