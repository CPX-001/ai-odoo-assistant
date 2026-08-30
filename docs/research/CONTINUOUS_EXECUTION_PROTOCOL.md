# Continuous execution protocol

Date: 2026-08-30  
Status: execution protocol, not architecture authority

## 1. Purpose

This document defines how independent AI/Codex/ChatGPT implementation runs resume the repository roadmap from Git without depending on chat memory.

It applies to both:

```text
FOUNDATION_STABILIZATION_PLAYBOOK.md   # P0-P4
AGENTIC_PRODUCT_EVOLUTION_PLAYBOOK.md # P5+
```

`EXECUTION_STATE.md` is always the current cursor.

## 2. Repository/source-of-truth order for every run

Read in this order:

1. applicable `AGENTS.md` files;
2. current `main` HEAD;
3. `docs/README.md`;
4. `docs/CURRENT_STATE.md`;
5. `docs/PRODUCT_VISION.md` when proposed work changes product behavior;
6. `docs/research/README.md`;
7. `docs/research/EXECUTION_STATE.md`;
8. active phase/slice record;
9. relevant section of the active playbook;
10. current code/tests/accepted ADRs relevant to the slice.

Current code + accepted ADRs outrank a stale playbook. If implementation evidence invalidates a plan assumption, reconcile documentation instead of forcing old design.

## 3. No GitHub Actions

Do not add, depend on or wait for GitHub Actions for this roadmap while repository instructions state no usable runners/workers are available.

Tests remain mandatory. Run them only in environments that genuinely provide their dependencies. Missing execution becomes validation debt, not PASS.

## 4. State vocabulary

```text
PENDING
READY
IN_PROGRESS
LOCAL_VALIDATION_REQUIRED
REAL_ENV_VALIDATION_REQUIRED
IMPLEMENTED_AWAITING_ORDERED_ACCEPTANCE
BLOCKED
COMPLETE
SUPERSEDED
```

`IMPLEMENTED_AWAITING_ORDERED_ACCEPTANCE` means code exists but formal predecessor/gate ordering prevents phase acceptance. It is not equivalent to COMPLETE.

## 5. Gate classes

### HARD

Must pass before downstream work that consumes the contract.

Typical HARD gates:

- authority/ACL/technical-profile behavior;
- approval/write/verification/recovery;
- provider event/identity/cancellation contracts;
- public event/stream schemas consumed by frontend;
- concurrency/ordering/snapshot contracts;
- Evidence/ACL/provenance contracts;
- privilege-boundary ADR/validation;
- measurements required to choose an architecture.

### SOFT

May remain debt only when explicitly classified and downstream design cannot be invalidated by failure.

A real-environment test is not automatically soft.

## 6. Bounded look-ahead

Look-ahead exists only to avoid idle time when a real gate cannot currently be run. It does not permit stacking dependent unvalidated architecture.

Default maximums:

```text
phase distance ahead: 1
implementation slices carrying unresolved real debt: 2
stacked unvalidated contract layers: 1
```

### Historical exception/debt

P3/P4 production code landed while the P2 real gate was pending. That bounded look-ahead was intentionally used to create a reproducible P2-P4 validation batch and was later accepted in order.

The general rule remains: do not stack a dependent production contract on top of a failed/unaccepted HARD contract merely to keep implementation moving.

## 7. Validation batching

Batch real gates when causality remains clear.

A failed HARD gate stops downstream acceptance immediately. Adjacent checks may be executed together when they validate one coherent product contract and a failure can still be attributed to a specific gate.

Do not create separate roadmap slices merely to mirror each validation command. Tests may be numerous while the implementation remains one coherent slice.

## 8. Slice sizing — maximize coherent value

The default unit of roadmap work is the **largest coherent slice that is still feasible to implement, understand, validate and recover safely**.

A good slice normally closes one meaningful product/architecture behavior end-to-end, including the relevant runtime/backend contract, frontend projection, deterministic coverage, documentation and cleanup. It should not stop after an arbitrary file, class, helper, test fixture or UI fragment when the same run can safely complete the behavior those pieces jointly implement.

Split a slice only when a real boundary requires it:

1. a HARD gate must be passed before dependent design is valid;
2. authority/security semantics deserve an independent review boundary;
3. one portion requires a materially different/unavailable execution environment;
4. rollback/recovery risk makes an intermediate checkpoint substantially safer;
5. the combined scope can no longer be reviewed or validated coherently in one run.

Do **not** split merely because:

- backend and frontend are different layers;
- tests live in separate files;
- documentation is separate from code;
- the GitHub/API tool produces multiple commits;
- a task can be described as several tiny implementation steps.

Commit granularity and slice granularity are different. A tool may mechanically create several commits while they still belong to one roadmap slice.

When in doubt, prefer fewer broader slices with explicit internal checkpoints and tests over many micro-slices that create partial-product ambiguity or make the roadmap harder to reconstruct.

## 9. Validation layers

Every slice defines applicable checks from:

### A. Static/contract

Code/schema/doc/ADR consistency and bounded contract inspection.

### B. Deterministic executable

Python/Odoo tests, JS/HOOT, protocol fixtures, standalone scripts.

### C. Agentic/product eval

Probabilistic task success, tool selection, grounding, continuity, etc. Repeat enough cases/runs to distinguish regressions from one unlucky generation.

### D. Real product-path

Real Odoo 18 + configured provider + browser/host environment where relevant. Use named IDs from `REAL_ENV_VALIDATION_PROTOCOL.md`.

Only executed successful checks may be recorded PASS.

## 10. Slice metadata

Every implementation slice records:

```text
id / phase / objective
inspected main HEAD
prerequisites
contracts/files affected
invariants
known failure modes
static/deterministic/eval validation
real validation IDs
gate types
look-ahead eligibility
validation debt created
exit criteria
docs/cleanup required
ADR requirement if any
```

Also record why the selected scope is the largest coherent feasible unit when the phase contains multiple nearby changes. Use `SLICE_TEMPLATE.md` where useful.

## 11. Recursive run algorithm

### Step 1 — reconstruct

Read Git state/order above. Never assume previous-chat state.

### Step 2 — reconcile concurrent changes

If `main` advanced, inspect changes before selecting/writing anything.

### Step 3 — process validation evidence first

New real/local evidence has priority over new feature work. A failed HARD gate immediately creates repair work and freezes dependent acceptance.

### Step 4 — select one coherent slice

Priority:

1. repair a failed HARD gate;
2. finish still-valid IN_PROGRESS work;
3. close validation debt if evidence is available;
4. select the first READY **coherent product slice**, grouping adjacent implementation work that can safely be completed and validated together;
5. only if blocked by unavailable real evidence, evaluate explicit look-ahead eligibility;
6. otherwise stop with exact required validation.

Do not convert each helper, file, frontend/backend layer or test into its own roadmap slice. Keep working inside the selected slice until the coherent product behavior is implemented or a genuine gate/risk boundary is reached.

### Step 5 — inspect reusable implementation

Search current repo before adding a subsystem. Reuse turn/capability/policy/evidence/queue primitives where possible.

Also inspect proven external Odoo patterns when they materially reduce design risk. Examples already documented:

- OCA `queue_job` for capacity/background semantics;
- OCA `base_import_async` for background imports;
- OCA `ai_tool`/Odoo AI Server Actions for declarative/reusable tools;
- Apexive for provider/Knowledge/domain-tool breadth.

Do not add a dependency merely because a pattern is useful.

### Step 6 — implement the largest coherent feasible slice

Complete the selected product behavior across all affected current-path layers when practical. Use internal checkpoints/tests as needed, but do not declare the slice finished while a required part of that same behavior is knowingly left for another micro-slice without a genuine boundary.

Preserve cross-phase invariants from the active playbook.

Important interpretation of the product direction:

> `No arbitrary shell/SQL/Python authority` does **not** mean `the final product may never operate the server`.

Technical operations are introduced only through explicit capabilities, technical profiles and privilege-boundary gates in their scheduled phase.

Similarly, `RAG is not implemented now` does not mean retrieval is unimportant; the P8/P9 Evidence/Knowledge contracts are deliberate future phases.

### Step 7 — validate what is available

Run relevant A/B/C checks. Run D when environment permits. Record exact commands/results, including tests not run.

### Step 8 — update state/evidence/docs

Before the run ends, update as applicable:

- active slice/phase record;
- `EXECUTION_STATE.md`;
- validation debt/gate status;
- `CURRENT_STATE.md` if implementation claims changed;
- relevant architecture/product document;
- accepted/new ADR where an invariant changed.

### Step 9 — publish coherent checkpoint

Commit/publish coherent changes to `main` according to repository policy. Do not claim a remote handoff that was not actually published.

Do not force-push/discard concurrent work.

### Step 10 — decide whether execution may continue

Continue inside the same slice while coherent required work remains and no genuine blocker exists. Select a new slice only after the current one reaches its actual boundary.

Stop when:

- a HARD gate blocks downstream work;
- look-ahead budget is exhausted;
- next work needs an ADR/product decision not already defined;
- required real evidence is unavailable and no independent preparation remains;
- continuing would make the slice too large to validate/recover coherently.

## 12. Current exact stop rule

`EXECUTION_STATE.md` is the only authoritative current stop rule. Historical phase-specific stop rules in earlier revisions are not current execution instructions.

A recurring run should process the exact active phase/slice and its blocking validation/repair work from that cursor rather than infer current work from old examples in this protocol.

## 13. External-reference rule

For a borrowed project pattern, record:

```text
reference + version/branch/commit when important
problem it solves here
parts reused conceptually
parts deliberately rejected
new dependency? yes/no and why
local tests/evals that decide acceptance
```

External popularity is not an architecture gate.
