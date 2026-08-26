# Architecture Decision Records

ADRs capture decisions that intentionally constrain the current architecture. They are authoritative together with current code; if implementation and an accepted ADR diverge, investigate the divergence rather than falling back to older milestone documents.

## Current accepted decisions

| ADR | Status | Decision |
| --- | --- | --- |
| ADR-014 | accepted | Unified host-authorized agent runtime; retire rigid workflow routing as the target architecture. |
| ADR-015 | accepted | Controlled batch capability/action foundation. |
| ADR-016 | accepted | Embedded Odoo runtime, Odoo-native persistence/cron queue, ephemeral Codex provider; retire operational sidecar. |
| ADR-017 | accepted | Addon Capability Framework with `CapabilityDefinition` as the atomic executable contract. |
| ADR-018 | accepted | Installation-scoped provider credentials plus database-scoped non-secret Codex activation. |

`ADR-000-template.md` is only the template.

## Authority

Use this order when deciding what is true now:

1. current code + accepted ADR;
2. current docs indexed by `../README.md`;
3. current tests;
4. historical milestone reports/task packets/research PDFs.

The old `docs/source-of-truth/` name does not make those PDFs more authoritative than newer ADRs/code. Their own recent Atlas/Benchmark snapshots require revalidation against `main`.

## Creating/superseding an ADR

Use an ADR for changes to durable architecture boundaries such as deployment unit, authority, persistence, capability contract, credential ownership or a major execution protocol. Do not edit an old accepted ADR to pretend a later decision was always part of it; add a superseding ADR and update this index/current docs.

Implementation-only refinements that remain inside an accepted decision normally belong in code/tests/current docs rather than a new ADR.