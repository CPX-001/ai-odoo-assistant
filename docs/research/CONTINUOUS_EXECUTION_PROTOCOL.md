# Continuous execution protocol

Inspected main: `b6a7b77bc91b7e80b25551d0c07334d396f68083`  
Date: 2026-08-26  
Status: execution protocol, not architecture authority

## Purpose

This document defines how an AI-assisted implementation loop may continue the stabilization roadmap over many separate runs without requiring a human to repeatedly say `continue`.

The protocol is intentionally restartable. Every run must reconstruct state from Git rather than relying on chat memory.

It applies to the roadmap in `FOUNDATION_STABILIZATION_PLAYBOOK.md` and to later research playbooks that opt into the same execution model.

## Scheduling constraint

The repository protocol is cadence-independent, but ChatGPT scheduled tasks currently cannot run more frequently than once per hour. A 40-minute ChatGPT recurrence is therefore not supported. Use an hourly recurrence when this protocol is driven by ChatGPT automation.

Do not encode cadence inside implementation state. A human, Codex session or another authorized execution environment may resume the same state at any time.

## No GitHub Actions for this roadmap

**Do not add or depend on GitHub Actions for roadmap execution, CI gates, scheduled continuation or live validation. This project currently has no GitHub-hosted/self-hosted runners available for this work.**

Consequences:

- do not create `.github/workflows/*` to advance phases;
- do not make a phase/slice exit gate depend on an Actions workflow;
- do not treat the absence of CI as permission to skip tests;
- deterministic tests must be run in an execution environment that actually has the repository/runtime available;
- Odoo+Codex integration gates must be run against the real supported environment and recorded explicitly;
- if an automated run cannot execute a required test, it must mark the test as pending rather than assume success.

This constraint may only be removed when the repository instructions are explicitly changed because runners have become available.

## Persistent state model

The loop uses four kinds of document:

```text
FOUNDATION_STABILIZATION_PLAYBOOK.md
    long-range ordered roadmap

EXECUTION_STATE.md
    single current cursor and blockers

PHASE*.md / slice records
    evidence and implementation history for the active phase

REAL_ENV_VALIDATION_PROTOCOL.md
    rules for tests that must be performed on real Odoo + Codex
```

Git is the memory between runs.

## State vocabulary

A phase or slice may have one of these states:

- `PENDING` — not started;
- `READY` — prerequisites satisfied and may be selected;
- `IN_PROGRESS` — current implementation work;
- `LOCAL_VALIDATION_REQUIRED` — code exists but deterministic/local verification has not been executed;
- `REAL_ENV_VALIDATION_REQUIRED` — only a real Odoo+Codex run can close the remaining gate;
- `BLOCKED` — cannot proceed until a named blocker is resolved;
- `COMPLETE` — implementation, required validation, documentation and cleanup are complete;
- `SUPERSEDED` — replaced after new evidence changed the plan.

Never translate `tests not runnable here` into `COMPLETE`.

## Slice sizing

A slice must be small enough to leave `main` coherent after one run.

A good slice normally changes one contract or one vertical behavior and includes its deterministic tests/documentation. Examples:

```text
P1.1 provider event contract
P1.2 Codex conformance fixtures
P1.3 unknown-notification compatibility
P2.1 FailureEnvelope dataclass/schema
P2.2 Codex error normalization
P2.3 browser error preservation
P3.1 public activity schema
P3.2 independent progress persistence
P4.1 provider answer-delta channel
```

If a selected slice cannot be completed safely within the current execution run, split it before implementation. Record child slices in `EXECUTION_STATE.md`; do not leave a half-migrated architecture merely to make progress visible.

## Required metadata for every slice

Before implementation, every active slice must identify:

```text
id
phase
objective
inspected_head
prerequisites
files/contracts likely affected
invariants
known failure modes
deterministic validation
real-environment validation
exit criteria
cleanup/docs required
```

Use `SLICE_TEMPLATE.md` when a separate slice record is useful.

## Recursive run algorithm

Every independent AI/Codex run follows this exact sequence.

### 1. Reconstruct state

Read, in order:

1. `AGENTS.md`;
2. latest `main` HEAD;
3. `docs/README.md`;
4. `docs/research/README.md`;
5. `docs/research/EXECUTION_STATE.md`;
6. active phase record;
7. relevant section of `FOUNDATION_STABILIZATION_PLAYBOOK.md`;
8. current code/tests/ADRs relevant to the selected slice.

Never continue from an old chat summary without re-reading the Git state.

### 2. Reconcile concurrent changes

Compare the HEAD recorded in execution state with current `main`.

If code changed materially:

- inspect the changes;
- revalidate assumptions;
- update the slice plan if necessary;
- do not blindly reapply an old patch.

### 3. Select exactly one next coherent slice

Selection order:

1. finish an `IN_PROGRESS` slice if it is still valid;
2. process validation evidence for a `LOCAL_VALIDATION_REQUIRED` or `REAL_ENV_VALIDATION_REQUIRED` slice if evidence is available;
3. otherwise select the first `READY` slice whose prerequisites are complete;
4. never jump to a later phase while the current phase exit gate remains open.

### 4. Inspect before writing

Inspect current implementation and tests. Search for reusable contracts first. If the discovered code contradicts the playbook, update the plan rather than forcing the planned design.

### 5. Implement the smallest coherent change

Requirements:

- preserve Odoo effective-user authority and `su=False`;
- preserve host-owned capability/schema/policy/approval/execution/verification;
- do not add parallel tool registries;
- do not revive sidecar-era runtime paths;
- no arbitrary SQL/Python/shell/sudo model tools;
- no GitHub Actions;
- remove obsolete current-path code if the slice makes it unnecessary.

### 6. Validate what the execution environment can actually validate

Three validation classes exist:

#### A. Static/repository validation

Examples: schema consistency, code inspection, fixtures, documentation coherence.

#### B. Deterministic executable validation

Examples: Python/Odoo unit tests, JS/HOOT tests, protocol fixtures, standalone test scripts.

Only mark these passed if the current execution environment actually ran them successfully.

#### C. Real environment validation

Requires real Odoo 18 Community + configured Codex and, where relevant, browser interaction. Follow `REAL_ENV_VALIDATION_PROTOCOL.md`.

An AI run without that environment must stop at `REAL_ENV_VALIDATION_REQUIRED` when this evidence is mandatory.

### 7. Update evidence and execution cursor

Before ending a run, update `EXECUTION_STATE.md` with:

- current HEAD/commit produced;
- slice state;
- what changed;
- tests actually run and their result;
- tests not run;
- real-environment checks still required;
- blockers;
- exact next slice/action.

Update the active phase record when implementation/evidence changes its exit gate.

### 8. Commit a coherent checkpoint

A run should end with one or more coherent commits on `main` per repository policy. Do not call unfinished work complete.

### 9. Decide whether the next automated run may continue

The next run may continue automatically only if state is one of:

- active slice still has safe implementation work remaining;
- active slice passed required validation and another slice is `READY`;
- validation evidence has appeared in the repository and can be processed.

The next run must not perform speculative work when state says:

- `REAL_ENV_VALIDATION_REQUIRED` and no new evidence exists;
- `BLOCKED`;
- phase exit requires a human product judgment;
- an architectural invariant needs a new ADR decision.

In these cases the automation should report the exact blocker and make no unrelated changes.

## Human/AI handshake for real-environment gates

A real-environment test is not an informal message such as `seems fixed`.

Each required test has an ID from `REAL_ENV_VALIDATION_PROTOCOL.md`. The human records or supplies enough sanitized evidence to decide pass/fail, for example:

```text
validation_id: P0-REAL-HELLO
commit: <sha tested>
Odoo version: 18.x
Codex version: <version>
result: PASS | FAIL
observed latency: ...
observed public activity: ...
observed UI error code/category: ...
notes: ...
```

Sensitive prompts, credentials, raw provider output and unrestricted tool arguments must not be committed merely as validation evidence.

## When a real test failure occurs

Do not immediately move the phase backward wholesale.

1. attach the failed validation ID to the current slice;
2. record observed vs expected behavior;
3. create the smallest corrective child slice;
4. implement + run deterministic regression tests;
5. repeat the same real validation ID;
6. only close the parent slice when the required validation passes.

This creates a reproducible feedback loop instead of ad-hoc `try another fix` development.

## Phase transition rule

A phase transition is allowed only when:

```text
all mandatory slices COMPLETE
AND deterministic exit gate PASS
AND mandatory real-env validation PASS
AND current docs updated
AND no unresolved recovery/security blocker
```

A phase report may itself implement a machine-readable gate evaluator, as Phase 0 already does. That evaluator is authoritative only for evidence it can actually observe; it may not fabricate browser or real-provider results.

## Suggested hourly automation instruction

When a ChatGPT scheduled task is used, its prompt should be conceptually equivalent to:

```text
Inspect CPX-001/ai-odoo-assistant main and follow AGENTS.md plus
`docs/research/CONTINUOUS_EXECUTION_PROTOCOL.md`.
Reconstruct the current cursor from `docs/research/EXECUTION_STATE.md`.
Work only on the next coherent pending slice in the active phase.
Inspect current code before modifying it. Run only validations genuinely available in the
execution environment; never claim unrun tests passed. Do not use GitHub Actions.
If real Odoo+Codex validation is required and no new evidence is available, make no speculative
next-phase changes: record/report the exact validation needed and stop.
Update execution state and phase evidence before finishing.
```

The prompt deliberately does not say `implement everything until finished`. The recursion comes from persisted state and repeated bounded runs.

## Why this is safer than a long autonomous run

The loop creates a checkpoint after every coherent slice:

```text
inspect -> implement -> validate -> checkpoint -> re-inspect -> next slice
```

This prevents several failures common in long agent runs:

- assumptions becoming stale after earlier code changes;
- multiple unrelated refactors accumulating before tests;
- falsely closing integration work that was never tested against Codex;
- proceeding to RAG/features while the provider/chat foundation is still broken;
- relying on private chain-of-thought or chat history as project state.

## Current starting point

At the inspected baseline, Phase 0 implementation tooling exists but its real Odoo+Codex exit gate is still open. `PHASE0_BASELINE.md` explicitly requires live captures before Phase 1.

Therefore the continuous loop must currently treat Phase 0 as active and stop at real-environment validation if those captures are not available.