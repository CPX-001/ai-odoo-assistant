# Phase 4 — real answer streaming

Date reconciled: 2026-08-28  
Runtime implementation baseline: `24b9460ad09998ec50d853e0a715b543e5991bbb`  
State: `COMPLETE`
Prerequisite: Phase 2 COMPLETE and Phase 3 COMPLETE

## Goal

Stream actual Assistant answer text before the final provider result while preserving the strict final structured decision as authority.

Activity, answer and terminal state are different concepts:

```text
activity.event  = safe host-known work
answer.delta    = provisional user-facing answer text
turn.final      = authoritative validated final result
turn.failure    = authoritative failure state
```

## Implemented production path

Current `main` includes:

- `StructuredFinalAnswerDeltaExtractor` for incremental structured-answer extraction;
- `StreamingCodexDecisionEngine` installed at the existing Codex provider seam;
- handling of `item/agentMessage/delta` from the real App Server stream;
- strict thread/turn/item identity and delta bounds;
- projection only of the user-facing `final_answer.answer` value;
- graceful disabling of provisional projection when structured fragments become unusable, while final validation remains authoritative;
- `answer.delta` emission into the existing context/live path;
- independent persisted answer items in `odoo.ai.turn.live.event`;
- authenticated browser live cursor consumption;
- separate `onActivity` and `onDelta` handling;
- final response reconciliation through `/turn/status`;
- browser gate scripts for first delta, parity, cancellation and fragmented UTF-8.

## Authority invariant

Provisional streamed text cannot:

- authorize a capability;
- create/modify an effect plan;
- bypass schema/policy/approval;
- establish final success;
- weaken failure/recovery semantics.

Only the final validated `NextDecision` returned by the provider boundary is authoritative.

## Current transport

The browser currently polls Odoo JSON/RPC live/status endpoints at bounded intervals.

This is real answer streaming at the product-data level even though transport is polling rather than SSE/WebSocket. Transport may be optimized later only from measurements; durability/cursor semantics remain authoritative.

## Deterministic coverage

Repository tests/harnesses cover:

- structured delta extraction across fragments;
- JSON/escape/UTF-8 boundaries;
- item/thread/turn mismatch rejection;
- invalid/oversized deltas;
- live-page normalization/cursor order;
- answer/activity separation;
- final reconciliation/no duplication;
- cancellation path;
- real browser runner preparation.

Relevant runbook:

```text
docs/research/PHASE34_REAL_VALIDATION_RUNBOOK.md
```

## Hard real gates

Accepted against checkpoint `8a4432dc9852eacc422b8c794b6613c75da702a9`:

```text
P4-REAL-FIRST-DELTA
P4-REAL-FINAL-PARITY
P4-REAL-CANCEL-STREAM
P4-REAL-UTF8-FRAGMENT
```

All four gates are `PASS`; see
`evidence/phase4/2026-08-28/P2-P4-REAL-ACCEPTANCE.md`.

### P4-REAL-FIRST-DELTA

A sufficiently long real response must expose at least one genuine answer fragment before terminal completion.

### P4-REAL-FINAL-PARITY

Concatenated provisional answer must reconcile with the authoritative final response without duplicated/lost prefix/suffix content.

### P4-REAL-CANCEL-STREAM

Cancel after streaming starts. No stale final answer may later be appended to the cancelled/current conversation.

### P4-REAL-UTF8-FRAGMENT

Real fragmented non-ASCII content (`España`, accents, `ñ`, emoji, etc.) must remain exact through provider/network/browser fragmentation.

## Failure rule

Any failed gate keeps Phase 4 unaccepted and blocks Phase 5. Repair the smallest provider/live/browser layer, add deterministic regression coverage and rerun the failed gate.

## Exit gate

Phase 4 becomes `COMPLETE` only when:

```text
Phase 2 COMPLETE
AND Phase 3 COMPLETE
AND relevant deterministic/Odoo/HOOT suites PASS
AND all four P4 real gates PASS
AND current docs/evidence updated
```

Phase 5 is now `READY`. The next selected slice is `P5.1 turn-scoped frontend/background state`
from `AGENTIC_PRODUCT_EVOLUTION_PLAYBOOK.md`.
