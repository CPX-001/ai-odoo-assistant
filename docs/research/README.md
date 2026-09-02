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
P0-P7 COMPLETE / ACCEPTED
P8.0 + P8.1/P8.2 FOUNDATION IMPLEMENTED
P8 FOCUSED VALIDATION / REAL GATES PENDING
P9+ NOT ELIGIBLE
```

P7 acceptance is anchored at `092ac57fe58a3a36765b115e78b2eca687f5dbbc`.
The current P8 Evidence foundation is implemented on `main` but is not accepted until
its focused and real gates execute successfully.

Use `EXECUTION_STATE.md` for the exact current SHA/cursor and validation debt.

## Primary current documents

| Document | Purpose |
| --- | --- |
| `EXECUTION_STATE.md` | Compact current cursor, blockers, accepted evidence and exact next action. |
| `P8_EVIDENCE_CORE_IMPLEMENTATION.md` | Implemented P8.0/P8.1/P8.2 foundation and explicit deferrals. |
| `P8_FOCUSED_VALIDATION_RUNBOOK.md` | Focused dependency-light/Odoo validation required before live Evidence expansion. |
| `CONTINUOUS_EXECUTION_PROTOCOL.md` | Restartable execution/validation rules. |
| `REAL_ENV_VALIDATION_PROTOCOL.md` | Named gates requiring real Odoo/provider/browser paths. |
| `PERIODIC_FULL_REGRESSION_RUNBOOK.md` | Canonical expensive broad regression when required. |
| `PRODUCT_BEHAVIOR_EVALS_V1.md` | Permanent user-visible product behavior baseline. |
| `P7_MINI_FRAMEWORK_IMPLEMENTATION.md` | Accepted Phase-7 extension-framework record. |

`P8_EVIDENCE_CORE_PREPARATION.md` is a completed historical preparation record and
must not be read as the current cursor.

## Current P7/P8 boundary

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

P8 extends that same seam with:

```text
CAPABILITY_PROVIDER_API_VERSION = "1"
reserved core namespaces
provider/guard failure isolation
EvidenceProvider
EvidenceProviderCatalog
EvidenceRoutingPolicy
EvidenceLedger
assistant.runtime_inventory
public User/Technical profile mapping
```

Trust/authority remains:

```text
Skill instructions       trusted behavior guidance, not authority
ContextProvider output   untrusted contextual data
Evidence content         untrusted data, never authority
manifest/provider data   derived host metadata, not authority
CapabilityDefinition     atomic executable unit
host registry/executor   final permission/policy/execution authority
```

## P8 validation next

Run the focused P8 gate before expanding live Evidence orchestration:

```text
focused dependency-light P8 tests
+ directly affected P7 extension/boundary tests
+ focused Odoo runtime-inventory Evidence test
+ static supported-surface cleanup checks
```

Repair failures at their owning layer and record exact execution evidence. Do not mark
P8 PASS from committed test files alone. The full regression is not implied unless the
active runbook/cursor or user requires it.

## Accepted evidence

P5/P6/P7 accepted evidence remains immutable historical proof. Important anchors:

```text
P5.8 evidence/phase5/2026-08-30/P5.8-REAL-ACCEPTANCE-688f569.md
P6 final evidence/regression/2026-08-31/FULL-REGRESSION-fc022a6.md
P7 acceptance evidence/phase7/2026-09-02/P7-ACCEPTANCE-092ac57.md
P7 final regression evidence/regression/2026-09-02/FULL-REGRESSION-092ac57.md
```

Older preparation/blocker records remain historical and must not be rewritten to
pretend they were already PASS at the time.

## External implementation references

External projects are design references, not requirements. Current useful patterns
include:

- Odoo Agents/Skills/Sources and Odoo-native link/`auto_install` modules;
- Pydantic AI capability composition/progressive disclosure;
- FastMCP provider composition;
- Apexive/OCA reusable tool/provider patterns;
- ERPipe typed safe-write/diagnostic workflows;
- OpenTelemetry GenAI naming/sensitive-content discipline.

The project keeps its stronger Odoo/host authority boundary and does not introduce a
framework merely to resemble a reference.

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
