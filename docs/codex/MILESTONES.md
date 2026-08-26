# Historical Codex milestone chronology

> **Historical record.** This file used to be the active milestone board for the sidecar-to-agent evolution. It is retained as chronology only. It does not define current scope, sequencing or deployment. Current entry points: [`../CURRENT_STATE.md`](../CURRENT_STATE.md), [`../ARCHITECTURE.md`](../ARCHITECTURE.md), [`README.md`](README.md) and accepted ADRs.

The original milestone/task packets remain under this directory and `tasks/`/`exec-plans/`. Their completion/next-step language should be interpreted relative to the commit/date they were written, not as an instruction for current `main`.

## Historical sequence

The repository progressed through several milestone families before the current embedded runtime: foundational service/delegation/security work; query/HOW_TO/explain/action paths; Codex App Server integration; unified agent/runtime cleanup; then migration of authority/persistence into the Odoo addon.

Those records remain useful for reconstructing design intent and regression/security lessons. They are deliberately not rewritten to pretend they described the present architecture.

## Current rule

Before starting new work, ignore historical “active milestone” labels and instead:

1. inspect current `main` and accepted ADRs;
2. read `docs/README.md` and `docs/CURRENT_STATE.md`;
3. identify current reusable capability/turn infrastructure;
4. consult a historical packet only if it explains a relevant earlier decision/test;
5. update current docs and tests with the new work.

A future roadmap should be created from current product problems/evals, not resumed from this historical milestone sequence.