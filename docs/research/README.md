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
P0-P8 COMPLETE / ACCEPTED
P8 FOCUSED VALIDATION PASS
P8 REAL EVIDENCE GATES PASS (6/6)
P9 ELIGIBLE / READY TO START
```

P8 acceptance is anchored at `e370af8acb7df175c0a90c8e17520c8576b4c6ce` and
documented in `evidence/phase8/2026-09-02/P8-ACCEPTANCE-e370af8.md`.

Use `EXECUTION_STATE.md` for the exact current SHA/cursor and validation debt.

## Primary current documents

| Document | Purpose |
| --- | --- |
| `EXECUTION_STATE.md` | Compact current cursor, blockers, accepted evidence and exact next action. |
| `P8_EVIDENCE_CORE_IMPLEMENTATION.md` | Accepted P8 implementation and explicit deferrals. |
| `P8_FOCUSED_VALIDATION_RUNBOOK.md` | Executed focused dependency-light/Odoo/real-gate scope. |
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
assistant.source_evidence
assistant.log_evidence
browser-safe citation metadata
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

## P8 validation result

The accepted gate executed:

```text
61 focused dependency-light tests
+ 20 focused Odoo/installed-addon tests
+ six real Odoo/Codex Evidence gates
+ static compile/lint/supported-surface checks
```

All passed. The full regression remains unexecuted periodic debt because the focused
runbook did not require it and no failure demonstrated wider blast radius.

## Accepted evidence

P5/P6/P7 accepted evidence remains immutable historical proof. Important anchors:

```text
P5.8 evidence/phase5/2026-08-30/P5.8-REAL-ACCEPTANCE-688f569.md
P6 final evidence/regression/2026-08-31/FULL-REGRESSION-fc022a6.md
P7 acceptance evidence/phase7/2026-09-02/P7-ACCEPTANCE-092ac57.md
P7 final regression evidence/regression/2026-09-02/FULL-REGRESSION-092ac57.md
P8 acceptance evidence/phase8/2026-09-02/P8-ACCEPTANCE-e370af8.md
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
