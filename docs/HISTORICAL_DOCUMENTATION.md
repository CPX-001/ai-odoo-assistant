# Historical and superseded documentation

The repository intentionally keeps milestone evidence from the former Assistant Service architecture. This index prevents that evidence from being mistaken for the current product.

## Why it is kept

Old task packets, gate reports and sidecar implementation notes are useful for security reasoning, regression tests and reconstructing why later ADRs were adopted. Rewriting them as if they had always described the embedded runtime would destroy that evidence.

## Global classification

| Path/pattern | Classification | Current replacement |
| --- | --- | --- |
| `docs/M1_*` through `docs/M7_*` | historical milestone reports | `CURRENT_STATE.md`, `ARCHITECTURE.md` |
| `docs/OPERATIONS_M1.md` | retired sidecar operations | `DEPLOYMENT_CONFIG.md` |
| `docs/M5_ROUTING_SECURITY.md` | superseded rigid workflow/router era | `UNIFIED_AGENT_RUNTIME.md`, ADR-014 |
| `docs/M6_ACTION_FOUNDATION.md` | predecessor action framework | `CAPABILITY_FRAMEWORK.md`, ADR-017 |
| `docs/codex/M*.md`, `docs/codex/MILESTONES.md` | historical milestone reports/workflows | `docs/codex/README.md`, current runtime docs |
| `docs/codex/tasks/**` | completed/superseded task packets | current code + ADRs; archive indexes in `tasks/README.md` and each `M*/README.md` |
| `docs/codex/exec-plans/**` | historical execution plans | root `PLANS.md`; archive `exec-plans/README.md` |
| `docs/third_party/**` | dated external audits | current code + re-check upstream; archive `third_party/README.md` |
| `docs/source-of-truth/*.pdf` | dated research snapshots | current code/ADRs; still design references |
| `docs/source-of-truth/build_*.py` | document build tooling | not runtime documentation |
| `design-qa.md` | UI QA snapshot | current UI code/tests |
| `service/**` | retired sidecar implementation lineage | embedded addon runtime; `service/README.md` marks boundary |
| `installer/**` | retired sidecar installer lineage | Odoo addon deployment; `installer/README.md` marks boundary |
| `migrations/**` + root `alembic.ini` | former Assistant DB migrations | Odoo addon lifecycle/migrations; `migrations/README.md` marks boundary |
| `tests/e2e/**` existing sidecar scripts | historical/regression E2E | current addon/Odoo E2E target documented in `tests/e2e/README.md` |

## Former current-looking documents now reconciled

`CHAT_PRODUCT_FLOW.md`, `HOW_TO_WORKFLOW.md`, `KNOWLEDGE_INDEX.md` and `AGENT_RUNTIME_OPTIMIZATION.md` have been rewritten against the embedded runtime. They no longer describe the old sidecar as current.

The old milestone directory READMEs under `docs/codex/tasks/M0` through `M7` have also been replaced with archive indexes. This removes stale “next milestone”, Assistant PostgreSQL and old Source-of-Truth instructions from the paths most likely to be mistaken for active backlog while preserving the individual historical packets unchanged.

## Close-out record

`DOCUMENTATION_AUDIT.md` records the repository-wide documentation audit and its exit criteria. It should be used as a checkpoint, not as a substitute for revalidating code after future runtime changes.

## Rule for future cleanup

A historical file can be deleted when it has no remaining audit/regression value, but it should not be silently revived. Any useful behavior must be reimplemented through the current embedded runtime and documented in a current document.
