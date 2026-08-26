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

## Current playbooks

| Document | Purpose |
| --- | --- |
| `FOUNDATION_STABILIZATION_PLAYBOOK.md` | Step-by-step path from the current fragile chat/runtime experience to a stable, observable, provider-neutral foundation before adding major RAG/features. |

## Rules for research documents

A research/playbook document should:

- start from current code, not from a PDF or external framework;
- distinguish observed behavior from proposed behavior;
- cite the exact external pattern being borrowed and also what is rejected;
- turn recommendations into ordered work packages with exit gates;
- make unsafe shortcuts and tempting out-of-order work explicit;
- define when an architectural decision needs an ADR;
- include tests/evals/metrics that decide whether the next phase is allowed to start.

The goal is to make progress possible without repeatedly redesigning the roadmap in chat.