# Research and execution guidance

This directory contains **living decision-support and implementation playbooks** derived from current repository inspection plus external research.

It is deliberately separate from the current-state documents in `docs/README.md`.

## Authority

Documents here do **not** override:

1. current code on `main` plus accepted ADRs;
2. current documents listed in `docs/README.md`;
3. deterministic tests exercising the current runtime.

They exist to answer a different question: **what should be done next, in what order, and what evidence is required before moving on?**

Every playbook must record the inspected commit and research date. Revalidate it when product code advances materially.

## Current execution documents

| Document | Purpose |
| --- | --- |
| `FOUNDATION_STABILIZATION_PLAYBOOK.md` | Step-by-step path from the current fragile chat/runtime experience to a stable, observable, provider-neutral foundation before adding major RAG/features. |
| `E2E_AGENT_LOOP_CONVERGENCE.md` | Detailed Apexive-vs-Assistant diagnosis and ordered convergence plan for a host-owned Codex decision loop without changing the UI or authority model. |
| `IMPLEMENTATION_PROMPT_CODEX_E2E.md` | Self-contained prompt for implementing the convergence one validated slice at a time. |
| `EXECUTION_STATE.md` | Persistent cursor for recursive/multi-run execution: active phase/slice, blockers, validations and exact next action. |
| `CONTINUOUS_EXECUTION_PROTOCOL.md` | Rules for repeatedly resuming the roadmap from Git without relying on chat memory, including slice sizing, stop rules and validation semantics. |
| `REAL_ENV_VALIDATION_PROTOCOL.md` | Named tests that must be performed against real Odoo 18 + Codex before selected slices/phases may close. |
| `ACTION_DIAGNOSTIC_EVIDENCE.md` | Sanitized boundary-level evidence required when debugging the active Phase 0 ACTION gate. |
| `SLICE_TEMPLATE.md` | Template for atomic roadmap slices with deterministic and real-environment gates. |
| `PHASE0_BASELINE.md` | Active execution record for the reproducible-baseline phase: scenario catalog, timing/error capture contract, implemented measurement hooks and the remaining exit-gate work. |

## Recursive execution rule

A repeated AI/Codex run must reconstruct the next action from `EXECUTION_STATE.md` and current `main`; it must not rely on the previous chat saying `continue`.

The intended loop is:

```text
inspect current main
-> read execution cursor
-> select one coherent slice
-> implement
-> run only tests genuinely available
-> request/consume real Odoo+Codex evidence when required
-> update state/evidence
-> commit coherent checkpoint
-> next run re-inspects from Git
```

If the active state is `REAL_ENV_VALIDATION_REQUIRED` and no new live evidence exists, the run must stop rather than start speculative later-phase work.

## No GitHub Actions

The current roadmap must **not** use GitHub Actions for scheduled continuation, CI gates or validation because no GitHub runners/workers are available for this project at present.

Tests still remain mandatory. They must be executed in an environment that actually has the required repository/Odoo/Codex runtime, and unrun tests must remain explicitly pending.

## Rules for research documents

A research/playbook document should:

- start from current code, not from a PDF or external framework;
- distinguish observed behavior from proposed behavior;
- cite the exact external pattern being borrowed and also what is rejected;
- turn recommendations into ordered work packages with exit gates;
- make unsafe shortcuts and tempting out-of-order work explicit;
- define when an architectural decision needs an ADR;
- include tests/evals/metrics that decide whether the next phase is allowed to start;
- distinguish deterministic validation from evidence that requires a real Odoo+Codex environment;
- never mark a phase complete because a test could not be run.

For active provider/ACTION failures, sanitized reports must preserve enough host-owned boundary metadata to identify the failing layer. Capability identifiers, normalized state/error codes, timings and bounded planning counts/source labels are acceptable; raw prompts, arguments/results, business values, credentials, provider stdout/stderr and private reasoning are not.

The goal is to make progress possible without repeatedly redesigning the roadmap in chat.
