# Continuous execution protocol

Date: 2026-08-28  
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

### Current exception/debt

P3/P4 production code is already landed while the P2 real gate is pending. This bounded look-ahead was intentionally used to create a reproducible P2-P4 validation batch.

Therefore current state treats look-ahead capacity as **exhausted**:

```text
P2 real gates pending
P3 code landed
P4 code landed
=> no P5 contract implementation until ordered P2 -> P3 -> P4 acceptance is processed
```

Preparation that cannot consume/change those contracts (documentation, test data, external research) may still be possible, but implementation of the P5 runtime/frontend contract is blocked.

## 7. Validation batching

Batch real gates when causality remains clear.

Current intended batch:

```text
run P2 gates
  if PASS -> run P3 gates
    if PASS -> run P4 gates
```

A failed gate stops downstream acceptance immediately.

Future phases may batch adjacent slices inside one phase after deterministic coverage, but a later phase cannot consume a failed/unaccepted HARD contract.

## 8. Validation layers

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

## 9. Slice metadata

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

Use `SLICE_TEMPLATE.md` where useful.

## 10. Recursive run algorithm

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
4. select first READY slice with all HARD prerequisites satisfied;
5. only if blocked by unavailable real evidence, evaluate explicit look-ahead eligibility;
6. otherwise stop with exact required validation.

### Step 5 — inspect reusable implementation

Search current repo before adding a subsystem. Reuse turn/capability/policy/evidence/queue primitives where possible.

Also inspect proven external Odoo patterns when they materially reduce design risk. Examples already documented:

- OCA `queue_job` for capacity/background semantics;
- OCA `base_import_async` for background imports;
- OCA `ai_tool`/Odoo AI Server Actions for declarative/reusable tools;
- Apexive for provider/Knowledge/domain-tool breadth.

Do not add a dependency merely because a pattern is useful.

### Step 6 — implement smallest coherent change

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

Continue only when another READY/eligible slice exists.

Stop when:

- a HARD gate blocks downstream work;
- look-ahead budget is exhausted;
- next work needs an ADR/product decision not already defined;
- required real evidence is unavailable and no independent preparation remains.

## 11. Current exact stop rule

At this revision, `EXECUTION_STATE.md` requires the five P2 real gates. P3/P4 implementation exists and must be accepted in order after P2.

Until that chain passes, a recurring implementation run should not start Phase 5 code.

It may:

- process new P2/P3/P4 evidence;
- repair a failing current gate;
- improve the validation harness without changing the unaccepted product contracts;
- keep docs/evidence coherent.

## 12. After P4 acceptance

Set Phase 5 READY and begin at:

```text
P5.1 turn-scoped frontend/background state
```

Do not skip directly to RAG/host operations/imports merely because those features are attractive. P5-P7 establish non-blocking UX, deep effect semantics and extension/self-awareness contracts that later functional layers consume.

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
