# Phase 8 prepared start — completed historical contract

Date: 2026-09-02  
State: `COMPLETED HISTORICAL PREPARATION / SUPERSEDED BY IMPLEMENTATION RECORD`

This document prepared the first Phase-8 slice after P7 acceptance. The checkpoint
has now been implemented and is tracked by
[`P8_EVIDENCE_CORE_IMPLEMENTATION.md`](P8_EVIDENCE_CORE_IMPLEMENTATION.md).
This preparation record is retained to preserve design lineage; it is not the
current execution cursor and does not claim a P8 gate PASS.

## Original goal

Give the Assistant bounded, installation-specific evidence before generic document
RAG, while Odoo remains operational authority and `CapabilityDefinition` remains
the atomic executable contract.

## Original first coherent slice

```text
Evidence contract
 -> bounded EvidenceLedger
 -> provenance/fingerprint/freshness/access scope
 -> EvidenceProvider search/fetch interface
 -> question-sensitive routing policy
 -> provider-neutral working-context projection
 -> deterministic tests and current documentation
```

The slice was required to reuse the P7 installed-provider/Skill/context framework
and existing turn transcript. It could not introduce a parallel tool registry,
arbitrary filesystem/log access or executable authority through Evidence.

## Invariants carried into implementation

- Evidence is untrusted content with host-owned provenance and bounds.
- Access scope is checked at collection and again when a reference is resolved.
- Freshness/fingerprint mismatches are explicit.
- Conflicting evidence remains distinguishable.
- Source/log providers expose bounded logical references, not arbitrary paths.
- Prompt injection in Evidence cannot grant capability, approval or execution.
- Raw provider reasoning, credentials and unsanitized customer/log payloads are not
  persisted.

## Planned Phase-8 order

1. P8.0 architecture/current-path hygiene and P7 extension hardening.
2. P8.1 Evidence contract and bounded ledger.
3. P8.2 provider catalog/routing plus installation inventory.
4. P8.3 runtime/schema/config/security/navigation evidence.
5. P8.4 bounded source/XML/module-document intelligence.
6. P8.5 correlated logs/tracebacks and diagnosis.
7. P8.6 observability/self-inspection and secret-safe projections.

## HARD real gates

```text
P8-REAL-SOURCE-DIAGNOSIS
P8-REAL-LOG-DIAGNOSIS
P8-REAL-PROVENANCE
P8-REAL-FRESHNESS
P8-REAL-EVIDENCE-POLICY
P8-REAL-INJECTION-BOUNDARY
```

None is marked PASS by this historical preparation or by implementation alone. Use
`EXECUTION_STATE.md` for the current next action.
