# Odoo AI Assistant documentation

This directory is the navigation layer for the project. It separates **what exists now**, **why the architecture looks this way**, **what the product is becoming**, and **how roadmap work is validated**.

If you only read three documents, read:

1. [`CURRENT_STATE.md`](CURRENT_STATE.md) — implementation truth in human terms.
2. [`ARCHITECTURE.md`](ARCHITECTURE.md) — current boundaries and invariants.
3. [`PRODUCT_VISION.md`](PRODUCT_VISION.md) — intended product direction.

## Choose your path

| I want to... | Start here | Then read |
|---|---|---|
| Understand the project from outside development | [`../README.md`](../README.md) | [`PRODUCT_VISION.md`](PRODUCT_VISION.md), component READMEs |
| Know what actually works today | [`CURRENT_STATE.md`](CURRENT_STATE.md) | [`research/EXECUTION_STATE.md`](research/EXECUTION_STATE.md) |
| Understand the runtime | [`ARCHITECTURE.md`](ARCHITECTURE.md) | [`UNIFIED_AGENT_RUNTIME.md`](UNIFIED_AGENT_RUNTIME.md) |
| Work on TaskPlan / multi-step effects | [`research/P6_PLANNING_EFFECTPLAN_IMPLEMENTATION.md`](research/P6_PLANNING_EFFECTPLAN_IMPLEMENTATION.md) | [`UNIFIED_AGENT_RUNTIME.md`](UNIFIED_AGENT_RUNTIME.md), active P6 cursor |
| Add or change a capability | [`CAPABILITY_FRAMEWORK.md`](CAPABILITY_FRAMEWORK.md) | [`../addons/odoo_ai_assistant/runtime/capabilities/README.md`](../addons/odoo_ai_assistant/runtime/capabilities/README.md) |
| Work on the agent/provider loop | [`UNIFIED_AGENT_RUNTIME.md`](UNIFIED_AGENT_RUNTIME.md) | [`adr/ADR-019-host-owned-iterative-decision-loop.md`](adr/ADR-019-host-owned-iterative-decision-loop.md) |
| Work on writes/actions | [`ARCHITECTURE.md`](ARCHITECTURE.md) | [`adr/ADR-014-unified-host-authorized-agent.md`](adr/ADR-014-unified-host-authorized-agent.md) |
| Understand accepted semantic activity/control UX | [`research/P5.8_IMPLEMENTATION.md`](research/P5.8_IMPLEMENTATION.md) | [`research/evidence/phase5/2026-08-30/P5.8-REAL-ACCEPTANCE-688f569.md`](research/evidence/phase5/2026-08-30/P5.8-REAL-ACCEPTANCE-688f569.md) |
| Configure/deploy Odoo + Codex | [`DEPLOYMENT_CONFIG.md`](DEPLOYMENT_CONFIG.md) | [`codex/README.md`](codex/README.md) |
| Understand query behavior | [`QUERY_CONTRACT.md`](QUERY_CONTRACT.md) | capability provider README |
| Follow current roadmap execution | [`research/EXECUTION_STATE.md`](research/EXECUTION_STATE.md) | active record referenced there |
| Validate in a real environment | [`research/REAL_ENV_VALIDATION_PROTOCOL.md`](research/REAL_ENV_VALIDATION_PROTOCOL.md) | relevant runbook/evidence folder |
| Understand why a major decision was made | [`adr/README.md`](adr/README.md) | the accepted ADR |
| Explore historical design | [`HISTORICAL_DOCUMENTATION.md`](HISTORICAL_DOCUMENTATION.md) | archive/source-of-truth material |

## Current architecture at a glance

```mermaid
flowchart TB
    UI[Web client / future surfaces] --> INV[Invocation + screen/user context]
    INV --> TURN[Odoo conversation + durable turn]
    TURN --> HOST[Provider-neutral host agent loop]
    HOST <--> MODEL[Current provider adapter: Codex]
    HOST --> TASK[TaskPlan: visible progress, no authority]
    HOST --> CAT[Effective capability catalog]
    CAT --> EXEC[CapabilityExecutor]
    EXEC --> ORM[Odoo ORM / bounded host service]
    HOST --> EFFECT[Typed EffectPlan → preview → policy/approval → execute → verify]
    EFFECT --> ORM
    HOST --> LIVE[Semantic activity + answer/reasoning presentation]
    TASK --> UI
    LIVE --> UI
```

Today this is an embedded Odoo runtime using Codex as the concrete reasoning provider. The core `NextDecisionEngine`, TaskPlan/EffectPlan semantics, capability framework, budgets and effect authority are provider-neutral.

General RAG, first-class Skills/Bundles, external `CapabilityProvider`, MCP, automations/AI fields, multiple production provider adapters and governed memory are later layers, not current claims.

## Current vs target notation

Documentation should make lifecycle status obvious:

- **Current / implemented:** code exists in the supported runtime.
- **Implemented candidate / validation pending:** code is on `main` but the required checkpoint/acceptance gate is still open.
- **Target / roadmap:** accepted product direction but not an implementation claim.
- **Historical / retired:** kept for lineage/evidence only.

Current formal state:

```text
P0-P5 COMPLETE
P6 IN_PROGRESS
  P6.1 TaskPlan vs EffectPlan        IMPLEMENTED_CANDIDATE
  P6.3 bounded multi-step EffectPlan IMPLEMENTED_CANDIDATE
  P6.5 separate budgets              FOUNDATION_IMPLEMENTED_CANDIDATE
```

No P6 HARD real gate is recorded PASS yet. The exact live cursor is always [`research/EXECUTION_STATE.md`](research/EXECUTION_STATE.md).

## Documentation layers

### Product and current state

- [`PRODUCT_VISION.md`](PRODUCT_VISION.md) — intended user experience and product boundaries.
- [`CURRENT_STATE.md`](CURRENT_STATE.md) — what is currently implemented, accepted or still missing.
- [`CHAT_PRODUCT_FLOW.md`](CHAT_PRODUCT_FLOW.md) — chat-facing flow and interaction contracts.
- [`research/P5.8_IMPLEMENTATION.md`](research/P5.8_IMPLEMENTATION.md) — accepted semantic activity/control/navigation/compensation implementation record.
- [`research/P6_PLANNING_EFFECTPLAN_IMPLEMENTATION.md`](research/P6_PLANNING_EFFECTPLAN_IMPLEMENTATION.md) — current TaskPlan/multi-step/budget implementation candidate and validation boundary.

### Architecture and subsystem contracts

- [`ARCHITECTURE.md`](ARCHITECTURE.md) — current system architecture.
- [`UNIFIED_AGENT_RUNTIME.md`](UNIFIED_AGENT_RUNTIME.md) — active agent/runtime contract.
- [`CAPABILITY_FRAMEWORK.md`](CAPABILITY_FRAMEWORK.md) — atomic capabilities, registry, executor and target extension model.
- [`QUERY_CONTRACT.md`](QUERY_CONTRACT.md) — bounded query semantics.
- [`KNOWLEDGE_INDEX.md`](KNOWLEDGE_INDEX.md) — knowledge/index direction; check `CURRENT_STATE.md` before treating it as active runtime.
- [`FUTURE_MODEL_ROUTING.md`](FUTURE_MODEL_ROUTING.md) — future provider/model routing ideas, not current product behavior.

### Operations and provider lifecycle

- [`DEPLOYMENT_CONFIG.md`](DEPLOYMENT_CONFIG.md)
- [`codex/README.md`](codex/README.md)
- [`codex/CODEX_AUTH.md`](codex/CODEX_AUTH.md)

`DEPLOYMENT_CONFIG.md` is the current deployment/configuration entry point; sidecar-era operations documents are historical.

### Architecture decisions

[`adr/`](adr/) contains accepted decisions. Important current foundation:

```text
ADR-016  Embedded Odoo runtime / one operational application
ADR-017  CapabilityDefinition as atomic capability contract
ADR-018  Superseded database-scoped Codex activation
ADR-019  Host-owned iterative decision loop
ADR-020  Host primary Codex session shared by the installation
```

An ADR explains a decision and trade-offs; current code may evolve under the same invariant or a newer accepted ADR.

### Research, roadmap and evidence

[`research/`](research/) contains execution playbooks, phase records and named acceptance evidence. These files are intentionally more procedural than the current architecture docs.

Always use [`research/EXECUTION_STATE.md`](research/EXECUTION_STATE.md) as the active roadmap cursor rather than inferring phase state from an older playbook.

## Component READMEs

```text
addons/odoo_ai_assistant/
├── README.md
├── controllers/README.md
├── models/README.md
├── services/README.md
├── runtime/README.md
│   ├── agent/README.md
│   └── capabilities/README.md
│       ├── adapters/README.md
│       └── providers/README.md
├── static/src/README.md
│   ├── components/README.md
│   └── services/README.md
├── security/README.md
├── data/README.md
├── migrations/README.md
├── views/README.md
├── tests/README.md
└── static/tests/README.md
```

## Source of truth

When sources disagree, normally prefer:

1. current code and accepted ADRs;
2. `CURRENT_STATE.md`, `ARCHITECTURE.md` and current subsystem contracts;
3. current tests and named real-environment evidence;
4. active research/playbooks;
5. dated reports and Project reference documents;
6. retired code/historical documentation.

External projects and research are design references, not requirements.

## Keeping docs useful

When changing a subsystem:

- update the nearest component README if its responsibility or extension boundary changed;
- update `CURRENT_STATE.md` when the product can or cannot do something materially different;
- update `ARCHITECTURE.md` for cross-component boundary changes;
- add/update an ADR when authority, deployment, persistence or a major invariant changes;
- update `research/EXECUTION_STATE.md` as part of governed roadmap/validation work;
- do not rewrite history to make an old report look current;
- mark target behavior as target until its tests/real gates are accepted.

A new reader should be able to answer quickly: **what is this piece for, how does it connect, how do I extend/replace it, and what must never be bypassed?**
