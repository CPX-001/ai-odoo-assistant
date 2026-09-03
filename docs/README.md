# Odoo AI Assistant documentation

Code on current `main` plus accepted ADRs is technical authority. Current-state docs
summarize that code; dated research/PDFs and external projects are design evidence.

## Current formal state

```text
P0-P11 COMPLETE / ACCEPTED
P11 accepted through 72b4b826bddffc20f99f5cd72f14ed95111eab5c
P12.1 BOUNDED SOURCE WORKSPACES IMPLEMENTED / FOCUSED VALIDATION PENDING
P12 NOT ACCEPTED
```

P11 acceptance evidence:
[`research/evidence/phase11/2026-09-03/P11-ACCEPTANCE-72b4b82.md`](research/evidence/phase11/2026-09-03/P11-ACCEPTANCE-72b4b82.md).

P12.1 adds no source-edit capability. It establishes the path/fingerprint/workspace
authority prerequisite defined by ADR-025 before P12.2 patch/diff work can begin.

## Primary reading path

1. [`CURRENT_STATE.md`](CURRENT_STATE.md) — supported implementation snapshot.
2. [`ARCHITECTURE.md`](ARCHITECTURE.md) — runtime and authority boundaries.
3. [`PRODUCT_VISION.md`](PRODUCT_VISION.md) — product direction.
4. [`CAPABILITY_FRAMEWORK.md`](CAPABILITY_FRAMEWORK.md) — executable extension contract.
5. [`EVIDENCE_ARCHITECTURE.md`](EVIDENCE_ARCHITECTURE.md) — retrieval/Evidence contract.
6. [`KNOWLEDGE_INDEX.md`](KNOWLEDGE_INDEX.md) — company Knowledge.
7. [`adr/ADR-024-technical-host-privilege-broker.md`](adr/ADR-024-technical-host-privilege-broker.md) — finite privileged host boundary.
8. [`adr/ADR-025-controlled-source-workspaces.md`](adr/ADR-025-controlled-source-workspaces.md) — P12 source/workspace/deploy authority prerequisite.
9. [`research/P12_SOURCE_WORKSPACE_FOUNDATION.md`](research/P12_SOURCE_WORKSPACE_FOUNDATION.md) — implemented P12.1 contract.
10. [`research/P12_FOCUSED_VALIDATION_RUNBOOK.md`](research/P12_FOCUSED_VALIDATION_RUNBOOK.md) — P12.1 focused gate and later real gates.
11. [`research/EXECUTION_STATE.md`](research/EXECUTION_STATE.md) — exact roadmap cursor.

## Architecture at a glance

```mermaid
flowchart TB
    UI[OWL chat / admin surfaces] --> TURN[Durable Odoo turn]
    TURN --> HOST[Provider-neutral host decision loop]
    HOST <--> MODEL[Codex App Server adapter]
    HOST --> EXT[Capabilities + Skills + Context + Evidence]
    EXT --> ORM[Effective-user Odoo ORM, su=False]
    HOST --> EFFECT[EffectPlan / policy / approval / verify]
    EFFECT --> ORM
    EFFECT --> BROKER[Optional typed P10 broker]
    EVID[Installed source/log/Knowledge Evidence] --> HOST
    SRC[Installed addon source] --> WS[P12 private bounded workspace]
    WS -. future P12.2/P12.3 .-> TEST[Typed diff + tests]
    TEST -. future P12.4 .-> DEPLOY[Separately authorized deployment]
```

Installed source and workspace contents are data/preconditions, not authority. The
model never receives a generic filesystem command surface.

## Current implementation records

```text
research/P11_ADVANCED_IMPORTS_FIRST_SLICE.md
research/P11_IMPORT_CLEANUP_REPAIR_SLICE.md
research/P11_FOCUSED_VALIDATION_RUNBOOK.md
research/P12_SOURCE_WORKSPACE_FOUNDATION.md
research/P12_FOCUSED_VALIDATION_RUNBOOK.md
research/REAL_ENV_VALIDATION_PROTOCOL.md
```

Historical evidence remains under `research/evidence/` and must not be rewritten to
make old states appear current.

## Status terminology

- **Implemented:** code exists on the supported path.
- **Implemented / validation pending:** code exists but required gates remain open.
- **Accepted:** required gates/evidence are green for the recorded lineage.
- **Target/proposed:** product direction only.
- **Historical:** retained for lineage/evidence.

No unexecuted gate may be represented as PASS.
