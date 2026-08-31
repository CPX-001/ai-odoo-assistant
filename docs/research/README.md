# Research and execution guidance

This directory contains living implementation playbooks, validation runbooks, product-eval specifications and named
evidence. Research documents do not override current code/accepted ADRs.

## Authority

When sources disagree, normally prefer:

1. current code on `main` plus accepted ADRs;
2. current architecture/subsystem docs;
3. current tests and accepted real evidence;
4. `EXECUTION_STATE.md` and active phase records;
5. older reports/external references.

Unexecuted validation is never PASS.

## Current cursor

```text
P0-P6 COMPLETE / ACCEPTED
P7 IMPLEMENTATION COMPLETE / ACCEPTANCE PENDING
P8+ NOT ELIGIBLE
```

The user requested that the remaining Phase-7 implementation be finished first and that accumulated tests plus
corrections be executed afterward. That implementation is now present; the next work is the consolidated validation
pass, not another P7 feature slice.

Use `EXECUTION_STATE.md` for the exact current SHA/cursor semantics.

## Primary execution documents

| Document | Purpose |
| --- | --- |
| `EXECUTION_STATE.md` | Current cursor, acceptance debt and exact next action. |
| `CONTINUOUS_EXECUTION_PROTOCOL.md` | Restartable execution/validation rules. |
| `REAL_ENV_VALIDATION_PROTOCOL.md` | Named gates requiring real Odoo/provider/browser paths. |
| `PERIODIC_FULL_REGRESSION_RUNBOOK.md` | Canonical expensive final regression. |
| `PRODUCT_BEHAVIOR_EVALS_V1.md` | Permanent user-visible product behavior baseline and 54-scenario catalog. |
| `PRODUCT_BEHAVIOR_EVALS_CODEX_HANDOFF.md` | Product Behavior implementation/real-gate handoff. |
| `P7_MINI_FRAMEWORK_IMPLEMENTATION.md` | Current complete Phase-7 implementation record. |
| `P7_CONSOLIDATED_VALIDATION_RUNBOOK.md` | Required next pass: P7 tests + Product Behavior + six P7 real gates + corrections. |
| `AGENTIC_PRODUCT_EVOLUTION_PLAYBOOK.md` | P5+ product roadmap and phase requirements. |
| `FOUNDATION_STABILIZATION_PLAYBOOK.md` | P0-P4 historical stabilization path. |

Accepted P5/P6 records and historical evidence remain in this directory and `evidence/`.

## Phase-7 implementation boundary

Current Phase-7 code includes:

```text
CapabilityProvider installed-addon discovery/composition
SkillDefinition / SkillCatalog
ContextProvider / ContextProviderCatalog
AssistantExtensionCatalog + live activation
ProviderProfile + current Codex binding
EffectiveAssistantManifest + admin diagnostics
Business/Developer technical profile skeleton
progressive-disclosure state contract with eager default
trusted P7 fixture addon + prepared tests
```

Trust/authority remains:

```text
Skill instructions       trusted behavior guidance, not authority
ContextProvider output   untrusted contextual data
manifest/provider data   derived host metadata, not authority
CapabilityDefinition     atomic executable unit
host registry/executor   final validation/permission/policy authority
```

The product stays eager for capability schemas until the disclosure gate shows that a lazy strategy improves cost
without harming task/tool-selection quality.

## Consolidated validation next

`P7_CONSOLIDATED_VALIDATION_RUNBOOK.md` defines the required order:

```text
P7 dependency-light/static
Product Behavior focused
installed fixture Odoo tests
Product Behavior SMOKE
six P7 real gates
Product Behavior FULL
final affected/full regression
```

Every HARD failure is repaired and rerun before Phase-7 acceptance.

## Accepted evidence through Phase 6

```text
P5.1 evidence/phase5/2026-08-28/P5.1-REAL-ACCEPTANCE-f7f924c.md
P5.2 evidence/phase5/2026-08-29/P5.2-REAL-ACCEPTANCE-b4fbb03.md
P5.3 evidence/phase5/2026-08-29/P5.3-REAL-ACCEPTANCE-32e836e.md
P5.4 evidence/phase5/2026-08-29/P5.4-REAL-ACCEPTANCE-3e2b38d.md
P5.5 evidence/phase5/2026-08-29/P5.5-REAL-ACCEPTANCE-8427c88.md
P5.6 evidence/phase5/2026-08-29/P5.6-REAL-ACCEPTANCE-720102f.md
P5.7 evidence/phase5/2026-08-29/P5.7-REAL-ACCEPTANCE-074a71c.md
P5.8 evidence/phase5/2026-08-30/P5.8-REAL-ACCEPTANCE-688f569.md
P6 final evidence/regression/2026-08-31/FULL-REGRESSION-fc022a6.md
```

The earlier P7.1 foundation evidence remains historical focused evidence only; it does not validate the later complete
Phase-7 integration.

## Product Behavior gate

Product Behavior v1 remains mandatory despite the user-directed sequencing change. It covers technical tests,
product-contract E2E and agentic behavior with:

- SMOKE and FULL suites;
- HARD authority/safety/user-contract graders;
- semantic quality scoring;
- normal/limited/admin personas;
- Spanish/Catalan/English cases;
- provider/tool timing;
- real answer streaming;
- Direct vs one-shot Plan;
- grounding/navigation/approval/batch/Stop/correction/multichat behavior.

Historical Phase-4 answer-streaming evidence cannot substitute for the new current-lineage real first-delta check.

## External implementation references

External Odoo/agent projects remain design references, not requirements. Useful concrete patterns include:

- OpenAI Agents namespaces/tool search for deferred large tool surfaces;
- Apexive `odoo-llm` reuse of one tool framework from chat and MCP;
- OCA `ai_tool` direction toward reusable tool definitions;
- Pydantic-style bundle separation above atomic tools.

The project keeps its stronger Odoo/host authority boundary and does not add those frameworks merely for resemblance.

## Execution rule

Each future run reconstructs from Git:

```text
inspect current main
 -> read EXECUTION_STATE
 -> process new validation evidence first
 -> repair failed HARD gate if present
 -> otherwise follow exact current next action
 -> update code/tests/docs/evidence coherently
```

No GitHub Actions are assumed while repository policy says usable runners are unavailable.
