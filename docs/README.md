# Documentation map

This file defines which repository documents describe the current product and which are retained as historical evidence.

## Authority order

When documents disagree, use:

1. current code on `main` plus accepted ADRs;
2. current documents in the table below;
3. current tests;
4. dated reports/task packets/research PDFs;
5. external references.

A dated document never overrides newer code. Architecture changes that intentionally break an accepted invariant require a new or superseding ADR.

## Current documents

| Document | Status | Purpose |
| --- | --- | --- |
| `CURRENT_STATE.md` | current | Audited snapshot of what exists now and what does not. |
| `ARCHITECTURE.md` | current | Runtime, authority, persistence and component boundaries. |
| `UNIFIED_AGENT_RUNTIME.md` | current | Turn lifecycle, reasoning/execution split and recovery. |
| `CAPABILITY_FRAMEWORK.md` | current | Atomic capability contract, registry/executor and extension direction. |
| `DEPLOYMENT_CONFIG.md` | current | Supported embedded deployment and configuration. |
| `QUERY_CONTRACT.md` | current | Schema-first query/discovery contract. |
| `codex/CODEX_AUTH.md` | current | Provider-owned Codex account lifecycle and database gate. |
| `adr/README.md` + accepted ADRs | current decisions | Architecture decision log. |
| `HISTORICAL_DOCUMENTATION.md` | current index | Classification of archived/superseded material. |

`CHAT_PRODUCT_FLOW.md`, `HOW_TO_WORKFLOW.md`, `KNOWLEDGE_INDEX.md` and `AGENT_RUNTIME_OPTIMIZATION.md` are retained as explicit migration/history notes and redirect to the current runtime where appropriate.

## Historical by default

The following material records earlier milestones and must not be read as current deployment/runtime instructions unless a current document explicitly links to a still-valid detail:

- root `docs/M*_*.md`, `docs/OPERATIONS_M1.md`, `docs/M5_ROUTING_SECURITY.md`, `docs/M6_ACTION_FOUNDATION.md`, `docs/M7_*`;
- `docs/codex/M*.md` milestone reports/workflows;
- everything under `docs/codex/tasks/` and `docs/codex/exec-plans/`;
- third-party audit snapshots under `docs/third_party/`;
- PDFs and generator scripts under `docs/source-of-truth/`;
- root `design-qa.md`, which is visual QA evidence for one UI snapshot.

See `HISTORICAL_DOCUMENTATION.md` for the reason and superseding current documents.

## Retired implementation lineage

`service/`, `installer/` and root `migrations/` describe or support the former Assistant Service architecture. They are not the current product runtime. Their local `AGENTS.md` files make this explicit.

## Updating documentation

Any change to current runtime behavior should update the relevant current document in the same commit. Do not rewrite historical reports to make them look as if they described the present; preserve their evidence and classify them clearly instead.