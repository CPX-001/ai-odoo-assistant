# Phase 3 — live public activity

Date reconciled: 2026-08-28  
Runtime implementation baseline: `24b9460ad09998ec50d853e0a715b543e5991bbb`  
State: `COMPLETE`
Prerequisite: Phase 2 all hard real gates PASS

This record supersedes `PHASE3_PUBLIC_ACTIVITY_PREPARATION.md` as the status record for production Phase 3. The preparation document remains useful historical evidence for how the contract was designed.

## Goal

Expose useful truthful host-known progress while a turn is actually running, without exposing private reasoning and without committing the business transaction merely to make the browser see progress.

Target channels remain distinct:

```text
public activity != assistant answer != private working transcript
```

## Implemented production path

Current `main` includes:

- closed bounded `PublicTurnEvent` contract;
- explicit allowed kind/phase/status/resource fields;
- private `agent.thinking`-style event rejection;
- trusted capability/public descriptor projection;
- independent `odoo.ai.turn.live.event` Odoo model;
- append path using a short independent Odoo cursor/transaction;
- committed turn binding without a foreign-key lock against the mutable worker row;
- no business-cursor commit from the live projection;
- authenticated `/odoo_ai/v1/turn/live` route;
- ordered sequence/cursor pagination;
- browser normalization and reconnect handling;
- current-activity + expandable activity-history UI.

Important design invariant:

> Live event persistence may report an already-known host lifecycle fact, but it may never authorize capability execution, mutate business records or weaken the write-barrier/recovery lifecycle.

## Representative activity lifecycle

Where safe descriptors exist, the host can project states such as:

```text
turn.started
provider.connecting
capability.started
capability.completed / failed
preview
awaiting approval
execution
verification
turn.completed / failed / cancelled
```

Activity labels/resources come from trusted host metadata and validated inputs/results. Raw provider reasoning is not a source of public activity text.

## Deterministic coverage

The repository contains contract/Odoo/browser tooling around:

- exact closed event parsing;
- cursor ordering and pagination;
- capability lifecycle projection;
- second-connection visibility before worker business commit;
- redaction/no arbitrary payload;
- frontend activity rendering/reconnect;
- real browser gate runner.

Relevant runbook:

```text
docs/research/PHASE34_REAL_VALIDATION_RUNBOOK.md
```

The existence of tests/harnesses alone is not real acceptance evidence. The real acceptance below
was recorded separately.

## Hard real gates

Accepted against checkpoint `ba4ba00f9a913854a21b571cbb4559105347cca2`:

```text
P3-REAL-ACTIVITY-READ
P3-REAL-ACTIVITY-ACTION
P3-REAL-LIVE-VISIBILITY
P3-REAL-REDACTION
```

All four gates are `PASS`; see
`evidence/phase4/2026-08-28/P2-P4-REAL-ACCEPTANCE.md`.

### P3-REAL-ACTIVITY-READ

A real bounded read must show relevant capability/model activity distinct from answer prose.

### P3-REAL-ACTIVITY-ACTION

A disposable effect must show prepare/approval/execution/verification lifecycle without bypassing the normal effect path.

### P3-REAL-LIVE-VISIBILITY

At least one meaningful live event must be visible through another browser/DB request before the worker business transaction is terminal/committed.

### P3-REAL-REDACTION

No credentials, raw prompt, private reasoning, unrestricted capability args/results or provider stdout/stderr may appear in the public feed.

## Failure rule

Any failed gate:

1. keeps Phase 3 unaccepted;
2. blocks Phase 4 acceptance;
3. creates the smallest Phase 3 repair slice;
4. adds deterministic regression coverage;
5. reruns the failed real gate.

## Exit gate

Phase 3 becomes `COMPLETE` only when:

```text
Phase 2 COMPLETE
AND deterministic relevant suites PASS on accepted code
AND all four P3 real gates PASS
AND current docs/evidence updated
```

Phase 4 subsequently completed its real acceptance gates on the same linear code lineage.
