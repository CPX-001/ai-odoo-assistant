# Phase 3 — public activity preparation

Date: 2026-08-28
Prepared checkpoint: `1a643cd948b2a68c941863e6d6f411b968afd61f`
State: `PREPARED_BLOCKED_BY_PHASE2_REAL`

## Scope decision

The execution protocol treats failure semantics -> public activity as a strong dependency. P2.4's five real gates are still a hard gate, so Phase 3 production persistence/browser behavior is not eligible. Only independent look-ahead preparation is committed.

## Prepared contract

`runtime/agent/public_activity.py` and `static/src/services/assistant_public_activity_contract.js` define matching closed bounded `PublicTurnEvent` parsers:

```text
sequence
turn_id
kind
phase
status
label
resource { model, record_ids, display_names }
capability
progress
diagnostic_code
occurred_at
```

Kinds/phases/statuses are closed, resource fields and batches are bounded, cursor order must strictly increase and one batch may contain only one turn. Extra fields fail closed. `agent.thinking` is explicitly invalid and there is no arbitrary payload field for prompts, tool arguments/results or private transcript.

`PublicCapabilityActivityDescriptor` is prepared as trusted-code metadata but is deliberately not wired into `CapabilityDefinition` before Phase 3 becomes eligible.

## Prepared real harness

`test_phase3_public_activity_real_gates.py` is tagged `-standard, phase3_real`. It is excluded from normal addon batteries and requires future production APIs:

```text
odoo.ai.turn.event.append_public_independent(...)
odoo.ai.turn.public_events_for_current_user(...)
```

LIVE-VISIBILITY opens two independent DB cursors: the worker appends without committing its business cursor and a second user connection must observe `capability.started` before worker completion. Browser timers are not evidence.

The same harness encodes reconnect cursor behavior, action lifecycle and redaction/private-kind rejection.

## Production plan after Phase 2 closes

First prove current event visibility. If current turn-event writes are not cross-request visible before the final business commit, add a short independent Odoo cursor/transaction for the closed public event only. It must never commit/authorize the business cursor, must preserve order/reconnect across workers and event-write failure must not become business authority.

Do not call `cr.commit()` on the main business transaction merely to make progress visible.

## Gates

```text
P3-REAL-ACTIVITY-READ    NOT RUN / BLOCKED_BY_PHASE2
P3-REAL-ACTIVITY-ACTION  NOT RUN / BLOCKED_BY_PHASE2
P3-REAL-LIVE-VISIBILITY  NOT RUN / BLOCKED_BY_PHASE2
P3-REAL-REDACTION        NOT RUN / BLOCKED_BY_PHASE2
```

Phase 3 is not IN_PROGRESS or COMPLETE. Phase 4 remains ineligible.
