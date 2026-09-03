# Architecture Decision Records

ADRs capture accepted constraints on the current architecture. Current code plus
accepted ADRs are primary technical authority; older milestone documents and Project
PDFs are design/history references.

## Current decisions

| ADR | Status | Decision |
| --- | --- | --- |
| ADR-014 | accepted | Unified host-authorized agent direction instead of rigid intent/workflow routing. |
| ADR-015 | accepted | Controlled batch/file-ingestion foundation. |
| ADR-016 | accepted | Embedded Odoo runtime, Odoo-native persistence/cron queue, ephemeral provider; retired operational Assistant sidecar. |
| ADR-017 | accepted | Addon Capability Framework; `CapabilityDefinition` is atomic executable authority. |
| ADR-018 | superseded by ADR-020 | Earlier database-scoped Codex activation decision. |
| ADR-019 | accepted, partly superseded by ADR-021 | Host-owned iterative provider decision loop. |
| ADR-020 | accepted | Host-configured primary Codex session with Odoo user/business authority kept separate. |
| ADR-021 | accepted | Provider-neutral TaskPlan, bounded multi-step EffectPlan, recovery units and EffectJournal. |
| ADR-022 | accepted | Bounded provider-neutral Evidence/ledger; provenance/freshness/access are host-owned and Evidence is non-executable. |
| ADR-023 | accepted | Host-owned observability with sanitized bounded telemetry rather than raw prompts/reasoning/secrets. |
| ADR-024 | accepted | Optional finite Technical host privilege broker; no root shell/passwordless sudo/general command surface. |
| ADR-025 | accepted | Controlled source changes are workspace-first; logical module roots + fingerprints before typed patch/test/deploy. |

`ADR-000-template.md` is only the template.

## Authority order

When sources disagree, normally use:

1. current code + accepted ADRs;
2. current docs indexed by `../README.md`;
3. current tests and accepted real evidence;
4. active execution state;
5. older research/PDFs/external references.

Do not rewrite an older accepted ADR to make a later decision look retroactive. Add a
new/superseding ADR and update the current index/state.
