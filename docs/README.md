# Odoo AI Assistant documentation

This directory separates current implementation, architectural authority, product
direction and validation evidence.

## Current formal state

```text
P0-P7 COMPLETE / ACCEPTED
P8.0 hardening + P8.1/P8.2 Evidence foundation IMPLEMENTED
P8 focused validation PENDING
P8 real gates NOT EXECUTED / NOT ACCEPTED
P9+ NOT ELIGIBLE
```

P7 remains accepted through `092ac57fe58a3a36765b115e78b2eca687f5dbbc`.
The P8 implementation record is
[`research/P8_EVIDENCE_CORE_IMPLEMENTATION.md`](research/P8_EVIDENCE_CORE_IMPLEMENTATION.md).
No new PASS evidence is inferred from code or prepared tests.

## Primary reading path

1. [`CURRENT_STATE.md`](CURRENT_STATE.md) — implementation snapshot in human terms.
2. [`ARCHITECTURE.md`](ARCHITECTURE.md) — runtime and authority boundaries.
3. [`PRODUCT_VISION.md`](PRODUCT_VISION.md) — product direction.
4. [`CAPABILITY_FRAMEWORK.md`](CAPABILITY_FRAMEWORK.md) — executable extension contract.
5. [`EVIDENCE_ARCHITECTURE.md`](EVIDENCE_ARCHITECTURE.md) — P8 retrieval/evidence contract.
6. [`OBSERVABILITY_ARCHITECTURE.md`](OBSERVABILITY_ARCHITECTURE.md) — trace/privacy contract.
7. [`research/EXECUTION_STATE.md`](research/EXECUTION_STATE.md) — exact roadmap cursor.

## Architecture at a glance

```mermaid
flowchart TB
    UI[OWL / future invocation surfaces] --> TURN[Odoo conversation + durable turn]
    TURN --> HOST[Provider-neutral host decision loop]
    HOST <--> MODEL[Codex App Server adapter today]
    HOST --> EXT[Effective Skills + JIT Context + Manifest]
    HOST --> EVC[Effective EvidenceProviderCatalog]
    EVC --> LEDGER[Bounded EvidenceLedger]
    HOST --> CAT[Effective CapabilityRegistry]
    CAT --> EXEC[CapabilityExecutor + policy]
    EXEC --> ORM[Odoo ORM / bounded host operation]
    HOST --> EFFECT[EffectPlan -> preview -> policy/approval -> execute -> verify]
    EFFECT --> ORM
    HOST --> LIVE[TaskPlan/activity/answer/final projection]
    LIVE --> UI
```

`CapabilityDefinition` remains executable authority. `CapabilityProvider`, Skills,
ContextProviders, EvidenceProviders, manifests and ledgers enrich discovery and
reasoning but cannot bypass registry/executor/policy.

## Current subsystem documents

### Product and runtime

- [`CURRENT_STATE.md`](CURRENT_STATE.md)
- [`PRODUCT_VISION.md`](PRODUCT_VISION.md)
- [`CHAT_PRODUCT_FLOW.md`](CHAT_PRODUCT_FLOW.md)
- [`ARCHITECTURE.md`](ARCHITECTURE.md)
- [`UNIFIED_AGENT_RUNTIME.md`](UNIFIED_AGENT_RUNTIME.md)
- [`TURN_LIFECYCLE_COMPOSITION.md`](TURN_LIFECYCLE_COMPOSITION.md)

### Capabilities, context and Evidence

- [`CAPABILITY_FRAMEWORK.md`](CAPABILITY_FRAMEWORK.md)
- [`EVIDENCE_ARCHITECTURE.md`](EVIDENCE_ARCHITECTURE.md)
- [`CONTEXT_SOURCE_POLICY.md`](CONTEXT_SOURCE_POLICY.md)
- [`QUERY_CONTRACT.md`](QUERY_CONTRACT.md)
- [`adr/ADR-022-evidence-core-and-ledger.md`](adr/ADR-022-evidence-core-and-ledger.md)

### Observability and future Technical boundary

- [`OBSERVABILITY_ARCHITECTURE.md`](OBSERVABILITY_ARCHITECTURE.md)
- [`adr/ADR-023-host-owned-observability.md`](adr/ADR-023-host-owned-observability.md)
- [`adr/ADR-024-technical-host-privilege-broker.md`](adr/ADR-024-technical-host-privilege-broker.md)
  — proposed only; no privileged broker is implemented.

### Execution, evals and evidence

- [`research/EXECUTION_STATE.md`](research/EXECUTION_STATE.md)
- [`research/P8_EVIDENCE_CORE_IMPLEMENTATION.md`](research/P8_EVIDENCE_CORE_IMPLEMENTATION.md)
- [`research/P8_FOCUSED_VALIDATION_RUNBOOK.md`](research/P8_FOCUSED_VALIDATION_RUNBOOK.md)
- [`research/P8_EVIDENCE_CORE_PREPARATION.md`](research/P8_EVIDENCE_CORE_PREPARATION.md)
  — completed historical preparation contract.
- [`research/REAL_ENV_VALIDATION_PROTOCOL.md`](research/REAL_ENV_VALIDATION_PROTOCOL.md)
- [`research/PRODUCT_BEHAVIOR_EVALS_V1.md`](research/PRODUCT_BEHAVIOR_EVALS_V1.md)
- [`research/PERIODIC_FULL_REGRESSION_RUNBOOK.md`](research/PERIODIC_FULL_REGRESSION_RUNBOOK.md)

## Supported-path cleanup

The embedded Odoo addon is the product runtime. The obsolete GitHub Actions workflow
that tested `service/`/`installer/` and the unauthenticated sidecar inventory
callback were removed in P8. Historical directories and evidence may remain for
lineage, but are excluded from current source context by
[`CONTEXT_SOURCE_POLICY.md`](CONTEXT_SOURCE_POLICY.md).

## Current versus target notation

- **Implemented:** code exists on the supported path.
- **Implemented / validation pending:** code exists but its required gate is open.
- **Accepted:** the required validation/evidence is green for that lineage.
- **Target/proposed:** product direction or ADR not yet implemented.
- **Historical:** retained only for lineage/evidence.

## Authority when documents disagree

Prefer:

1. current code and accepted ADRs;
2. current architecture/subsystem documents;
3. current tests and accepted real evidence;
4. active execution state;
5. dated research, reports and external references.

External projects and Project PDFs provide patterns, not execution authority.

## Documentation maintenance

When a subsystem changes, update the nearest current contract and the execution
cursor in the same checkpoint. Do not rewrite historical evidence to look current
and never label an unexecuted gate PASS.
