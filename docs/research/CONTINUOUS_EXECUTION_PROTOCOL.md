# Continuous execution protocol

Inspected main: `4eb8502e04f54feccc5ad47a69fb5d0a51910416`  
Date: 2026-08-26  
Status: execution protocol, not architecture authority

## Purpose

This document defines how an AI-assisted implementation loop may continue the stabilization roadmap over many separate runs without requiring a human to repeatedly say `continue`.

The protocol is restartable: every run reconstructs state from Git rather than relying on chat memory.

It applies to `FOUNDATION_STABILIZATION_PLAYBOOK.md` and to later research playbooks that opt into the same execution model.

The protocol intentionally allows **bounded look-ahead** when a real-environment validation is pending and the next work does not depend on the unvalidated behavior. It does **not** allow several dependent architecture layers to accumulate without validation.

## Scheduling constraint

The repository protocol is cadence-independent, but ChatGPT scheduled tasks currently cannot run more frequently than once per hour. A 40-minute ChatGPT recurrence is therefore not supported. Use an hourly recurrence when this protocol is driven by ChatGPT automation.

Do not encode cadence inside implementation state. A human, Codex session or another authorized execution environment may resume the same state at any time.

## No GitHub Actions for this roadmap

**Do not add, modify, depend on or wait for GitHub Actions for roadmap execution, scheduled continuation or validation gates. This project currently has no GitHub-hosted/self-hosted runners available for this work.**

An existing workflow in `.github/workflows/` may remain as historical/independent repository infrastructure, but this roadmap must not treat it as an available worker or CI authority.

Consequences:

- do not create roadmap workflows under `.github/workflows/`;
- do not make a phase/slice exit gate depend on Actions;
- do not treat the absence of CI as permission to skip tests;
- deterministic tests must run in an execution environment that actually has the required repository/runtime;
- Odoo+Codex integration gates must run against the real supported environment and be recorded explicitly;
- if an automated run cannot execute a required test, it records validation debt instead of assuming success.

This constraint may only be removed when repository instructions are explicitly changed because usable runners exist.

## Persistent state model

The loop uses four kinds of document:

```text
FOUNDATION_STABILIZATION_PLAYBOOK.md
    long-range ordered roadmap

EXECUTION_STATE.md
    current cursor, validation debt, blockers and look-ahead budget

PHASE*.md / slice records
    evidence and implementation history for active work

REAL_ENV_VALIDATION_PROTOCOL.md
    tests that must be performed on real Odoo + Codex
```

Git is the memory between runs.

## State vocabulary

A phase or slice may have one of these states:

- `PENDING` — not started;
- `READY` — prerequisites satisfied;
- `IN_PROGRESS` — implementation work is active;
- `LOCAL_VALIDATION_REQUIRED` — deterministic/local verification is still pending;
- `REAL_ENV_VALIDATION_REQUIRED` — implementation is ready for a real Odoo+Codex gate;
- `BLOCKED` — cannot proceed until the named blocker is resolved;
- `COMPLETE` — implementation, mandatory validation, docs and cleanup are complete;
- `SUPERSEDED` — replaced because later evidence changed the design.

Do not translate `tests not runnable here` into `COMPLETE`.

## Gate classes

Every validation dependency that can block downstream work is classified as either `HARD` or `SOFT`.

### HARD gate

A hard gate must be satisfied before implementing work that relies on the unvalidated assumption.

Typical hard gates:

- failing deterministic tests;
- security, ACL, authority, approval, verification or recovery semantics;
- provider protocol/identity/cancellation contracts consumed by later layers;
- a public event/schema contract that downstream frontend/transport code will depend on;
- baseline measurements required to choose between architecture alternatives;
- an ADR decision that changes a current invariant;
- evidence whose failure would materially change the next slice design.

Example:

```text
Codex provider event contract unvalidated
    -> do not build answer streaming on top of it
```

### SOFT gate

A soft gate may remain as validation debt while narrowly independent work continues.

Typical soft gates:

- final product polish checks that do not alter the consumed contract;
- a larger soak/performance confirmation after mechanics are already deterministically verified;
- documentation, fixtures, eval datasets or test harness preparation independent of the blocked runtime contract;
- a real UX confirmation when the next slice only prepares unrelated backend/eval infrastructure.

A real-environment test is not automatically soft. Its classification depends on what later work assumes from its result.

## Bounded look-ahead policy

The purpose of look-ahead is to avoid wasting development time while waiting for a convenient real Odoo+Codex validation session. It is not permission to defer integration testing indefinitely.

Default limits for the stabilization roadmap:

```text
maximum phase distance ahead: 1
maximum implementation slices carrying unresolved real-env debt: 2
maximum stacked unvalidated contract layers: 1
```

Interpretation:

- it is acceptable to prepare one or two independent slices and then validate them together;
- it is usually acceptable to prepare work from the immediately following phase if it does not consume the unvalidated contract;
- it is **not** acceptable to implement two or three complete dependent phases and test them only afterwards;
- a downstream slice that consumes a new unvalidated contract counts as another contract layer and is blocked when the stack would exceed 1.

For phases 1 through 5 of the current stabilization roadmap, assume strong dependency by default:

```text
provider boundary
    -> failure semantics
        -> public activity
            -> answer streaming
                -> chat UX
```

Therefore these phases should not be accumulated wholesale without validation.

## Validation batching

Real-environment validations should be batched when doing so does not hide causality.

A useful rhythm is:

```text
slice A -> deterministic tests
slice B -> deterministic tests
    -> one Odoo+Codex validation session covering A+B
    -> process failures
    -> next batch
```

This is preferable to forcing a human validation after every tiny refactor.

A batch ends immediately when:

- a hard gate fails;
- the next slice would consume an unvalidated contract;
- the unresolved debt would exceed the look-ahead budget;
- a security/write/recovery invariant is affected;
- the next decision depends on performance/behavior not yet measured.

## Validation debt

`EXECUTION_STATE.md` must explicitly list every unresolved validation rather than hiding it inside prose.

Each debt item should record:

```text
validation_id
gate_type: HARD | SOFT
origin_slice
commit_materially_tested: <sha or pending>
downstream_scope_blocked
reason
```

Validation debt may accumulate only within the look-ahead budget. `COMPLETE` still means mandatory debt for that slice is cleared.

If a later commit materially changes the subsystem covered by an older PASS, the relevant validation becomes debt again.

## Look-ahead eligibility test

Before selecting work while the current phase has unresolved validation, answer all of these:

1. Does the proposed slice consume any new behavior/contract that is still unvalidated?
2. Could failure of the pending validation require redesigning this slice?
3. Does the slice touch security, writes, recovery, provider identity/cancellation or authority?
4. Would it create a second stacked unvalidated contract layer?
5. Would total unresolved implementation slices exceed the configured budget?
6. Does the current phase explicitly mark its gate as hard for this downstream scope?

If any answer is `yes`, the slice is not look-ahead eligible unless `EXECUTION_STATE.md` contains an explicit researched exception.

Good look-ahead examples:

- build Codex protocol fixtures/conformance harness while Phase 0 waits for live baseline evidence, without changing runtime behavior;
- prepare failure/eval datasets and fault-injection fixtures while a provider soak is pending;
- improve test tooling/documentation that remains valid whichever provider adapter wins.

Bad look-ahead examples:

- replace the provider adapter before Phase 0 measurements needed to choose the design;
- implement public activity on a provider event contract that has not passed its hard conformance gate;
- implement answer streaming on top of unverified live event visibility;
- optimize process lifecycle before latency attribution exists;
- stack UI behavior on error/event contracts that may still change after real tests.

## Slice sizing

A slice must be small enough to leave `main` coherent after one run.

Examples:

```text
P1.1 provider event contract
P1.2 Codex conformance fixtures
P1.3 unknown-notification compatibility
P2.1 FailureEnvelope schema
P2.2 Codex error normalization
P2.3 browser error preservation
P3.1 public activity schema
P3.2 independent progress persistence
P4.1 provider answer-delta channel
```

If a selected slice cannot be completed safely in one run, split it before implementation. Do not leave a half-migrated architecture merely to make progress visible.

## Required metadata for every slice

Before implementation, every active slice identifies:

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
gate_type
lookahead_eligible
validation_debt_created
depends_on_unvalidated_contracts
exit criteria
cleanup/docs required
```

Use `SLICE_TEMPLATE.md` when a separate slice record is useful.

## Recursive run algorithm

Every independent AI/Codex run follows this sequence.

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

Never continue from an old chat summary without re-reading Git state.

### 2. Reconcile concurrent changes

Compare the HEAD recorded in execution state with current `main`. If code changed materially, inspect the changes and revalidate assumptions before writing.

### 3. Process available validation evidence first

If new Odoo+Codex or local evidence has appeared, process it before starting more look-ahead work. A failed hard gate freezes dependent slices immediately.

### 4. Select one coherent slice

Selection order:

1. repair a failed hard gate or finish a still-valid `IN_PROGRESS` slice;
2. close validation debt when evidence is available;
3. select the first normal `READY` slice whose hard prerequisites are satisfied;
4. if blocked only by unavailable real-environment evidence, evaluate an explicitly allowed look-ahead slice;
5. if none is eligible, stop and report the exact validation required.

### 5. Inspect before writing

Inspect current implementation and tests. Search for reusable contracts first. If code contradicts the playbook, update the plan instead of forcing the planned design.

### 6. Implement the smallest coherent change

Requirements:

- preserve effective-user Odoo authority and `su=False`;
- preserve host-owned capability/schema/policy/approval/execution/verification;
- do not add parallel tool registries;
- do not revive sidecar-era runtime paths;
- no arbitrary SQL/Python/shell/sudo model tools;
- no GitHub Actions for roadmap work;
- remove obsolete current-path code when the slice makes it unnecessary.

### 7. Validate what is genuinely available

Validation classes:

#### A. Static/repository validation

Schema consistency, code inspection, fixtures, documentation coherence.

#### B. Deterministic executable validation

Python/Odoo unit tests, JS/HOOT tests, protocol fixtures and standalone test scripts.

Only mark them passed if they actually ran successfully.

#### C. Real environment validation

Requires real Odoo 18 Community + configured Codex and, where relevant, browser interaction. Follow `REAL_ENV_VALIDATION_PROTOCOL.md`.

If unavailable, create/update validation debt and apply the hard/soft/look-ahead rules above.

### 8. Update evidence and cursor

Before ending a run, update `EXECUTION_STATE.md` with:

- current HEAD/commit produced;
- slice state;
- what changed;
- tests actually run and results;
- tests not run;
- validation debt;
- look-ahead budget consumption;
- blockers;
- exact next action.

Update the active phase record when implementation/evidence changes its exit gate.

### 9. Commit a coherent checkpoint

A run should end with coherent commits on `main` per repository policy. Do not call unfinished work complete.

### 10. Decide whether another automated run may continue

Continue automatically only when:

- implementation work remains safe and coherent;
- a normal next slice is `READY`; or
- an eligible look-ahead slice fits inside the budget.

Stop when:

- a hard validation blocks the proposed downstream scope;
- validation debt is at the configured limit;
- the next slice would create another unvalidated contract layer;
- state is `BLOCKED`;
- an ADR/product judgment is required.

## Human/AI handshake for real-environment gates

A real test is not an informal `seems fixed` message.

Each required test has an ID from `REAL_ENV_VALIDATION_PROTOCOL.md`. Record sanitized evidence such as:

```text
validation_id: P4-REAL-FIRST-DELTA
commit: <sha tested>
Odoo version: 18.x
Codex version: <version>
result: PASS | FAIL
observed latency: ...
observed public activity: ...
observed UI error code/category: ...
notes: ...
```

Do not commit credentials, private reasoning, raw provider output or sensitive unrestricted tool payloads as validation evidence.

## When a real test failure occurs

1. attach the failed validation ID to the originating slice;
2. record observed vs expected behavior;
3. freeze dependent look-ahead slices;
4. mark affected downstream work `BLOCKED`, `SUPERSEDED` or in need of revalidation as appropriate;
5. create the smallest corrective child slice;
6. add deterministic regression coverage;
7. repeat the same real validation;
8. revalidate downstream slices whose assumptions were affected.

The look-ahead budget deliberately limits the amount of code that can require this rework.

## Phase transition rule

A phase is formally complete only when:

```text
all mandatory slices COMPLETE
AND deterministic exit gate PASS
AND mandatory hard real-env validation PASS
AND mandatory soft validation debt for phase completion cleared
AND current docs updated
AND no unresolved recovery/security blocker
```

Look-ahead can begin before formal completion only under the bounded policy. It does not change the phase-completion definition.

## Suggested hourly automation instruction

```text
Inspect CPX-001/ai-odoo-assistant main and follow AGENTS.md plus
`docs/research/CONTINUOUS_EXECUTION_PROTOCOL.md`.
Reconstruct the cursor and validation debt from `docs/research/EXECUTION_STATE.md`.
Process new validation evidence first. Work on the next coherent normal slice, or on one explicitly
look-ahead-eligible slice if the current blocker is only unavailable real Odoo+Codex validation and
the look-ahead budget permits it. Never stack dependent unvalidated contracts.
Inspect current code before modifying it. Run only validations genuinely available; never claim
unrun tests passed. Do not use GitHub Actions for this roadmap.
Update execution state, validation debt and phase evidence before finishing.
```

## Current starting point

At this protocol revision, Phase 0 implementation tooling exists but the real Odoo+Codex exit evidence is still missing.

Phase 0 remains a **hard gate for architecture-changing Phase 1 runtime/provider refactors** because its measurements and failure observations are meant to prevent design-by-guessing.

However, one immediately useful Phase 1 preparation lane is safe while waiting: protocol/conformance fixtures and harness work that does not modify product runtime behavior. `EXECUTION_STATE.md` records the exact authorized look-ahead scope.
