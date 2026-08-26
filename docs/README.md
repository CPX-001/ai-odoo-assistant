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
| `CHAT_PRODUCT_FLOW.md` | current | Browser-to-Odoo chat/turn/progress lifecycle. |
| `HOW_TO_WORKFLOW.md` | current status | HOW_TO behavior inside the unified agent; no separate router. |
| `KNOWLEDGE_INDEX.md` | current status | Current retrieval gap and constraints for future embedded knowledge/RAG. |
| `AGENT_RUNTIME_OPTIMIZATION.md` | current | Performance/quality guidance for the embedded runtime. |
| `DEPLOYMENT_CONFIG.md` | current | Supported embedded deployment and configuration. |
| `QUERY_CONTRACT.md` | current | Schema-first query/discovery contract. |
| `codex/CODEX_AUTH.md` | current | Provider-owned Codex account lifecycle and database gate. |
| `adr/README.md` + accepted ADRs | current decisions | Architecture decision log. |
| `HISTORICAL_DOCUMENTATION.md` | current index | Classification of archived/superseded material. |
| `DOCUMENTATION_AUDIT.md` | close-out record | Repository-wide documentation reconciliation baseline and exit criteria. |

## Research and execution guidance

`docs/research/` contains living research and ordered implementation playbooks. These documents do **not** describe implemented product behavior and do not override the current documents/ADRs above. Their purpose is to turn repository inspection plus external research into explicit next steps, work packages and exit gates.

Current entry points:

- `research/README.md` — scope, authority and rules for research/playbook documents;
- `research/FOUNDATION_STABILIZATION_PLAYBOOK.md` — ordered path for provider stability, failure contracts, live public activity, real answer streaming, chat UX, latency measurement, regression gates and capability-framework evolution before major feature/RAG expansion.

When a playbook item is implemented, update the authoritative current document/ADR that describes the resulting behavior. Do not treat a checked roadmap item as architecture authority by itself.

## Historical by default

The following material records earlier milestones and must not be read as current deployment/runtime instructions unless a current document explicitly links to a still-valid detail:

- root `docs/M*_*.md`, `docs/OPERATIONS_M1.md`, `docs/M5_ROUTING_SECURITY.md`, `docs/M6_ACTION_FOUNDATION.md`, `docs/M7_*`;
- `docs/codex/M*.md` milestone reports/workflows and `docs/codex/MILESTONES.md`;
- everything under `docs/codex/tasks/` and `docs/codex/exec-plans/` except their archive README files;
- third-party audit snapshots under `docs/third_party/` except its archive README;
- PDFs and generator scripts under `docs/source-of-truth/`;
- root `design-qa.md`, which is visual QA evidence for one UI snapshot.

Every `docs/codex/tasks/M0/README.md` through `M7/README.md` is now an **archive index** for its directory, not a milestone status/backlog document. Individual task packets remain unchanged so their historical acceptance evidence is preserved.

See `HISTORICAL_DOCUMENTATION.md` for the reason and superseding current documents.

## Retired implementation lineage

`service/`, `installer/` and root `migrations/` describe or support the former Assistant Service architecture. They are not the current product runtime. Their local `AGENTS.md`/README entry points make this explicit.

## Plans/task packets

Root `PLANS.md` defines current planning rules. `docs/codex/TASK_PACKET_TEMPLATE.md` is the current hand-off template. Old packets/plans are archives, not backlog.

## Documentation close-out

`DOCUMENTATION_AUDIT.md` records the 2026-08-26 repository-wide close-out performed before feature expansion. It states the inspected implementation baseline, current-vs-historical classification, external sanity checks and intentional non-changes.

## Updating documentation

Any change to current runtime behavior should update the relevant current document in the same commit. Do not rewrite historical reports to make them look as if they described the present; preserve their evidence and classify them clearly instead.
