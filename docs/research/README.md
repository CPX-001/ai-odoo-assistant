# Research and execution guidance

This directory contains implementation records, validation runbooks, product-eval
specifications and named evidence. Research history does not override current code or
accepted ADRs.

## Authority

When sources disagree, normally prefer:

1. current code on `main` plus accepted ADRs;
2. current architecture/subsystem docs;
3. current tests and accepted real evidence;
4. `EXECUTION_STATE.md` and the active phase record;
5. older reports/external references.

Unexecuted validation is never PASS.

## Current cursor

```text
P0-P9 COMPLETE / ACCEPTED
P10 PRIVILEGE-BOUNDARY ADR ACCEPTED
P10 TYPED HOST-OPERATIONS FIRST SLICE IMPLEMENTED
P10 FOCUSED VALIDATION PASS
P10 REAL VALIDATION PENDING
P10 MODULE-UPDATE ADAPTER NOT IMPLEMENTED
```

P9 remains the latest accepted phase, anchored at
`77d470febf67ddee46562907718dc47e975922bb` and documented in
`evidence/phase9/2026-09-03/P9-ACCEPTANCE-77d470f.md`.

Use `EXECUTION_STATE.md` for the exact cursor, implementation lineage, blockers and
validation debt.

## Primary current documents

| Document | Purpose |
| --- | --- |
| `EXECUTION_STATE.md` | Compact current cursor, blockers, accepted evidence and exact next action. |
| `P10_HOST_OPERATIONS_FIRST_SLICE.md` | Implemented Technical/broker boundary and explicit deferrals. |
| `P10_FOCUSED_VALIDATION_RUNBOOK.md` | Focused and real validation required for the first P10 slice. |
| `P9_KNOWLEDGE_FIRST_SLICE.md` | Accepted P9 Knowledge implementation record. |
| `P9_FOCUSED_VALIDATION_RUNBOOK.md` | Executed P9 validation scope and acceptance link. |
| `P8_EVIDENCE_CORE_IMPLEMENTATION.md` | Accepted P8 implementation and explicit deferrals. |
| `CONTINUOUS_EXECUTION_PROTOCOL.md` | Restartable execution/validation rules. |
| `REAL_ENV_VALIDATION_PROTOCOL.md` | Named gates requiring real Odoo/provider/host/browser paths. |
| `PERIODIC_FULL_REGRESSION_RUNBOOK.md` | Canonical expensive broad regression when required. |
| `PRODUCT_BEHAVIOR_EVALS_V1.md` | Permanent user-visible product behavior baseline. |
| `P7_MINI_FRAMEWORK_IMPLEMENTATION.md` | Accepted Phase-7 extension-framework record. |

Older preparation records are historical and must not be read as the current cursor.

## Current P7-P10 boundary

Accepted P7 provides:

```text
CapabilityProvider installed-addon discovery/composition
SkillDefinition / SkillCatalog
ContextProvider / ContextProviderCatalog
AssistantExtensionCatalog
ProviderProfile
EffectiveAssistantManifest
progressive-disclosure state model
```

Accepted P8/P9 extend that same seam with Evidence and Knowledge:

```text
EvidenceProvider / EvidenceProviderCatalog
EvidenceRoutingPolicy / EvidenceLedger
assistant.runtime_inventory
assistant.source_evidence
assistant.log_evidence
assistant.company_knowledge
assistant.knowledge.ingest_attachment
browser-safe citations and stale/freshness checks
```

The implemented P10 first slice adds:

```text
accepted ADR-024 machine privilege boundary
odoo.module.inspect
postgres.health
odoo.config.inspect / odoo.config.patch
host.service.status / host.service.restart
optional AF_UNIX broker with logical-target policy
peer credentials, bounded protocol and durable replay ledger
post-dispatch uncertainty preservation
```

Trust/authority remains:

```text
Skill instructions       trusted behavior guidance, not authority
ContextProvider output   untrusted contextual data
Evidence content         untrusted data, never authority
manifest/provider data   derived host metadata, not authority
CapabilityDefinition     atomic executable unit
host registry/executor   final Odoo permission/policy authority
broker policy            final privileged target/operation authority
```

The broker is not a third human profile and not another Assistant runtime. It cannot
be used by a User/non-technical profile merely because autonomy is high.

## Validation truth

Accepted P8/P9 evidence remains immutable. P10 focused static, dependency-light and
Odoo tests pass at `bbfa78b`; the real-environment runbook remains pending.

Current P10 blockers:

```text
focused dependency-light tests                   PASS — 14 tests
focused Odoo tests                               PASS — 4 tests, 0 failures/errors
broker deployment/systemd smoke                  NOT EXECUTED — deployment absent
profile/config/service/postgres/boundary gates   NOT EXECUTED
P10-REAL-MODULE-UPDATE                           BLOCKED — maintenance adapter missing
P10 acceptance                                   NOT COMPLETE
```

The full repository/addon/HOOT/Product Behavior regressions remain periodic debt
unless a focused failure or explicit instruction widens the required scope.

## Accepted evidence

Important immutable anchors:

```text
P5.8 evidence/phase5/2026-08-30/P5.8-REAL-ACCEPTANCE-688f569.md
P6 final evidence/regression/2026-08-31/FULL-REGRESSION-fc022a6.md
P7 acceptance evidence/phase7/2026-09-02/P7-ACCEPTANCE-092ac57.md
P7 final regression evidence/regression/2026-09-02/FULL-REGRESSION-092ac57.md
P8 acceptance evidence/phase8/2026-09-02/P8-ACCEPTANCE-e370af8.md
P9 acceptance evidence/phase9/2026-09-03/P9-ACCEPTANCE-77d470f.md
```

Older preparation/blocker records remain historical and must not be rewritten to
pretend they were already PASS at the time.

## External implementation references

External projects are design references, not requirements. Useful patterns include:

- Odoo Agents/Skills/Sources and Odoo-native module/lifecycle behavior;
- Pydantic AI capability composition/progressive disclosure;
- FastMCP provider composition;
- Apexive/OCA reusable tool/provider patterns;
- ERPipe typed safe-write/diagnostic workflows;
- OpenTelemetry GenAI naming/sensitive-content discipline;
- Linux AF_UNIX peer credentials, systemd hardening and fixed-argv service control.

The project keeps its stronger Odoo/host authority boundary and does not introduce a
framework or general shell merely to resemble a reference.

## Execution rule

Every future run reconstructs from Git:

```text
inspect current main
 -> read EXECUTION_STATE + current implementation record
 -> process new validation evidence first
 -> repair failed HARD gate if present
 -> otherwise follow exact current next action
 -> update code/tests/docs/evidence coherently
```

No GitHub Actions are used for this roadmap while repository policy says runners are
not the supported validation path.
