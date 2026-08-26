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
| `docs/codex/tasks/**` | completed/superseded task packets | current code + ADRs; archive `tasks/README.md` |
| `docs/codex/exec-plans/**` | historical execution plans | root `PLANS.md`; archive `exec-plans/README.md` |
| `docs/third_party/**` | dated external audits | current code + re-check upstream; archive `third_party/README.md` |
| `docs/source-of-truth/*.pdf` | dated research snapshots | current code/ADRs; still design references |
| `docs/source-of-truth/build_*.py` | document build tooling | not runtime documentation |
| `design-qa.md` | UI QA snapshot | current UI code/tests |
| `service/**` | retired sidecar implementation lineage | embedded addon runtime |
| `installer/**` | retired sidecar installer lineage | Odoo addon deployment |
| `migrations/**` | former Assistant DB migrations | Odoo model/schema migrations in addon lifecycle |
| `tests/e2e/**` existing sidecar scripts | historical/regression E2E | current addon/Odoo E2E target documented in `tests/e2e/README.md` |

## Former current-looking documents now reconciled

`CHAT_PRODUCT_FLOW.md`, `HOW_TO_WORKFLOW.md`, `KNOWLEDGE_INDEX.md` and `AGENT_RUNTIME_OPTIMIZATION.md` have been rewritten against the embedded runtime. They no longer describe the old sidecar as current.

## Rule for future cleanup

A historical file can be deleted when it has no remaining audit/regression value, but it should not be silently revived. Any useful behavior must be reimplemented through the current embedded runtime and documented in a current document.