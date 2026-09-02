# Phase 8 prepared start — evidence core and installation intelligence

Date: 2026-09-02  
State: `READY_TO_START / NO P8 IMPLEMENTATION CLAIMED`

Phase 7 is accepted at `092ac57fe58a3a36765b115e78b2eca687f5dbbc`. Phase 8 therefore has no
prerequisite validation debt and may start from this packet.

## Goal

Give the Assistant bounded, installation-specific evidence before generic document RAG, while Odoo
remains operational authority and `CapabilityDefinition` remains the atomic executable contract.

## First coherent slice

Implement P8.1 and the minimum P8.2 routing seam together:

```text
Evidence contract
 -> bounded EvidenceLedger
 -> provenance/fingerprint/freshness/access scope
 -> EvidenceProvider search/fetch interface
 -> question-sensitive routing policy
 -> provider-neutral working-context projection
 -> deterministic tests and current documentation
```

The slice must reuse the P7 installed-provider/Skill/context framework and existing turn transcript;
it must not introduce a parallel tool registry, arbitrary filesystem/log access or executable
authority through evidence.

## Required invariants

- Evidence is untrusted content with host-owned provenance and bounds.
- Access scope is checked at collection and again when a reference is resolved.
- Freshness/fingerprint mismatches are explicit, never silently accepted.
- Conflicting evidence remains distinguishable; no source is universally authoritative.
- Source/log providers expose bounded logical references and excerpts, never arbitrary paths.
- Prompt injection in evidence cannot grant capabilities, approval or execution.
- Raw provider reasoning, credentials and unsanitized customer/log payloads are never persisted.

## Planned order

1. P8.1 Evidence contract + bounded ledger.
2. P8.2 provider interface and routing policy.
3. P8.3 runtime/schema/config evidence.
4. P8.4 bounded source/XML intelligence.
5. P8.5 correlated structured logs/tracebacks.

## HARD real gates

```text
P8-REAL-SOURCE-DIAGNOSIS
P8-REAL-LOG-DIAGNOSIS
P8-REAL-PROVENANCE
P8-REAL-FRESHNESS
P8-REAL-EVIDENCE-POLICY
P8-REAL-INJECTION-BOUNDARY
```

No P8 gate is claimed PASS in this preparation record. The next action is implementation of the
first coherent slice, followed by its focused deterministic/Odoo boundaries.
