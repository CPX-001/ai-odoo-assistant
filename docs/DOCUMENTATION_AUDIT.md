# Documentation close-out audit

Date: 2026-08-26

This is the close-out record for the repository-wide documentation reconciliation before new feature expansion. The implementation baseline inspected for current-product claims is code commit `a16825b159a25caca3b48fcab15b9b21b0169ab6`; the documentation sweep continued from `2ab4d66f4c3b80228fdc6f1bb6fcabf12637dccf`. Documentation-only commits after that code baseline do not change product behavior.

## Goal

Make it unambiguous which files describe the product **now**, which files are architectural decisions, and which files are historical/research evidence. The audit does not delete history or rewrite old reports to pretend they described the embedded runtime.

## Authority established

When sources disagree:

1. current code on `main` + accepted ADRs;
2. current documents indexed by `docs/README.md`;
3. tests that exercise the current embedded runtime;
4. dated milestone reports/task packets/research snapshots;
5. external references.

The directory name `docs/source-of-truth/` is historical and does not change this order.

## Current documentation checked/reconciled

The active set is intentionally small:

- root `README.md`, `AGENTS.md`, `PLANS.md`;
- `docs/CURRENT_STATE.md`;
- `docs/ARCHITECTURE.md`;
- `docs/UNIFIED_AGENT_RUNTIME.md`;
- `docs/CAPABILITY_FRAMEWORK.md`;
- `docs/CHAT_PRODUCT_FLOW.md`;
- `docs/QUERY_CONTRACT.md`;
- `docs/HOW_TO_WORKFLOW.md`;
- `docs/KNOWLEDGE_INDEX.md`;
- `docs/AGENT_RUNTIME_OPTIMIZATION.md`;
- `docs/DEPLOYMENT_CONFIG.md`;
- `docs/codex/CODEX_AUTH.md`;
- `docs/adr/README.md` and accepted ADRs;
- addon/test/local `AGENTS.md` and addon README files.

These now describe the embedded Odoo runtime rather than the retired FastAPI sidecar.

## Current implementation claims preserved

The reconciled documentation consistently records that:

- the supported product is the Odoo 18 Community addon `odoo_ai_assistant`;
- the browser talks to Odoo, not directly to a separate Assistant service;
- conversations/turns/events are persisted in Odoo and long work is claimed by `ir.cron` workers;
- business capabilities execute under the effective Odoo Environment with `su=False` and normal ACL/record-rule/field/company enforcement;
- `CapabilityDefinition` is the atomic executable contract and host-side registry/schema/policy/approval/execution/verification remain authoritative;
- Codex App Server is a provider subprocess owned by the Odoo runtime identity; provider credentials remain in private `CODEX_HOME` below Odoo `data_dir`;
- the current core capability provider modules are `odoo_query`, `odoo_actions`, `odoo_batch` and `odoo_runtime`;
- general embedded document/vector RAG, first-class Skills/Bundles, external-addon `CapabilityProvider`, MCP product exposure, governed long-term memory, automations/AI fields and multimodal ingestion are not documented as completed current features.

## Historical material policy

Historical evidence remains intentionally available, but current-looking entry points have been neutralized:

- root milestone/gate reports are classified by `HISTORICAL_DOCUMENTATION.md`;
- `docs/codex/README.md` and `docs/codex/MILESTONES.md` mark the old milestone sequence historical;
- `docs/codex/tasks/README.md` and every `M0`–`M7` task-directory README mark task packets as archive evidence rather than backlog;
- `docs/codex/exec-plans/README.md` marks old execution plans historical;
- `docs/source-of-truth/README.md` classifies PDFs as dated research snapshots;
- `docs/third_party/README.md` classifies external audits as dated snapshots;
- `service/README.md`, `installer/README.md` and `migrations/README.md` make retired sidecar code/config visible as historical when browsing those trees;
- root `design-qa.md` is explicitly a historical UI QA snapshot.

Individual historical reports/task packets are not rewritten. Their stale architecture/milestone wording is part of the evidence they preserve; parent indexes and the global documentation map define their status.

## External sanity checks

The close-out also rechecked two fast-moving external boundaries on 2026-08-26:

- Odoo 18 official security documentation still confirms ACLs, record rules and field access as core server-side authority mechanisms; this supports, but does not replace, the repository's effective-user security design.
- OpenAI's current public Codex App Server description confirms a bidirectional stdio/JSONL client protocol and thread/event model. The repository-specific choice to launch/use it with bounded lifecycle remains an internal architecture decision, not something inferred from the public article.

External documentation never overrides current repository code/ADRs.

## Intentional non-changes

This documentation pass does **not**:

- restore the sidecar runtime;
- delete historical code/reports/tests;
- claim old sidecar RAG/source/log features are present in the embedded capability catalog;
- turn project research PDFs into requirements;
- add a new framework, service, database or feature;
- alter product behavior.

## Exit criteria

The documentation baseline is considered closed when:

- current entry points no longer describe the retired sidecar as operational architecture;
- current-vs-historical authority is explicit from root, `docs/`, Codex task areas and retired implementation trees;
- current feature gaps are stated as gaps rather than silently inherited from historical milestones;
- accepted ADRs and current docs point to the same deployment/authority/capability model;
- future feature work can start from `CURRENT_STATE.md` without reconstructing repository history first.

This close-out satisfies those criteria for the inspected baseline. Any later runtime change must update the relevant current documentation in the same change.
