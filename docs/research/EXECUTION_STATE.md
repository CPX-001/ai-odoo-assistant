# Stabilization execution state

State format: 58  
Updated: 2026-09-02

## Accepted lineage

```text
P0-P4 through 8a4432dc9852eacc422b8c794b6613c75da702a9
P5.1 through f7f924ce944db86e896745fef83ea2fb6fd6583a
P5.2 through b4fbb034e113a41c26db77cb274f2b3b30f6eee3
P5.3 through 32e836e7789ea72f3ba0d32fe6bdabbb092f5953
P5.4 through 3e2b38d68fe172cd2cf92d7794159f73476ac23d
P5.5 through 8427c8849b1e1f3afa6337de1209a6027410c266
P5.6 through 720102f2a13af5240c779b07cc71ee65994a87b1
P5.7 through 074a71c29a6a6109ae7412e7b1f9850c4449e379
P5.8 through 688f569d441a40a4637ad6a23f111e584e18c955
P6 final acceptance through 0b1bcab39b71dfbe02526cda7cf7ac8e218ac4b0
P7 final acceptance through 092ac57fe58a3a36765b115e78b2eca687f5dbbc
```

P0-P7 remain accepted. No P8 validation result changes that lineage yet.

## Current cursor

```text
phase: 8
phase_name: evidence core and installation intelligence
active_slice: P8.0-HARDENING + P8.1/P8.2-FOUNDATION
slice_state: IMPLEMENTED_FOCUSED_VALIDATION_PENDING
implementation_record: docs/research/P8_EVIDENCE_CORE_IMPLEMENTATION.md
focused_validation_runbook: docs/research/P8_FOCUSED_VALIDATION_RUNBOOK.md
active_real_validation_runbook: docs/research/REAL_ENV_VALIDATION_PROTOCOL.md
current_gate_type: P8_FOCUSED_DEPENDENCY_LIGHT_AND_ODOO
blocking_implementation: none for the foundation checkpoint
blocking_validation: focused P8 tests and affected P7/addon boundaries have not been executed in an Odoo/Codex-capable environment
latest_accepted_evidence: docs/research/evidence/regression/2026-09-02/FULL-REGRESSION-092ac57.md
latest_phase_acceptance: docs/research/evidence/phase7/2026-09-02/P7-ACCEPTANCE-092ac57.md
next_action: execute focused P8 dependency-light tests, product-profile/boundary tests, focused Odoo runtime-inventory test and directly affected P7 extension tests; repair failures before live Evidence orchestration
```

## Implemented foundation

```text
obsolete sidecar-testing GitHub workflow removed
unauthenticated sidecar inventory callback removed
addon-local residual machine-auth primitive/exports removed
versioned CapabilityProvider API + reserved namespaces
optional provider/guard failure isolation + deep immutable contracts
Evidence contracts, logical locators and access/freshness checks
EvidenceProviderCatalog + question-sensitive routing seam
bounded EvidenceLedger
Skills activated from effective Evidence provider IDs
runtime/installation inventory EvidenceProvider
public User/Technical product-profile mapping
source-scope descriptor and current architecture/ADRs
current-state/capability/product/research docs synchronized to P8
focused dependency-light and Odoo tests prepared
```

This means code exists. It does not mean the focused tests or P8 real gates passed.
The live provider-neutral decision loop still needs the next integration slice to
select/fetch Evidence during model-driven turns and surface citations end to end.

## Immediate focused validation

Run at minimum:

```text
tests/unit/test_phase8_evidence_contracts.py
tests/unit/test_phase8_evidence_runtime.py
tests/unit/test_phase8_extension_evidence.py
tests/unit/test_phase8_supported_surface.py
tests/unit/test_phase8_product_profiles.py
tests/addon/test_phase8_runtime_evidence.py
tests/addon/test_addon_boundaries.py
```

Also run directly affected existing tests for:

```text
P7 CapabilityProvider composition and failure isolation
Skill/Context/manifest projection
provider-neutral Codex trust partitions
```

The exact commands and environment are in
`docs/research/P8_FOCUSED_VALIDATION_RUNBOOK.md`. A full regression is not implied
merely because this checkpoint is on `main`; expand only for a concrete failure or an
explicit runbook requirement.

## Validation debt

```text
P8 focused dependency-light                         NOT EXECUTED
P8 focused Odoo                                     NOT EXECUTED
P8 live Evidence search/fetch/citation              NOT IMPLEMENTED / NOT EXECUTED
P8-REAL-SOURCE-DIAGNOSIS                            NOT EXECUTED
P8-REAL-LOG-DIAGNOSIS                               NOT EXECUTED
P8-REAL-PROVENANCE                                  NOT EXECUTED
P8-REAL-FRESHNESS                                   NOT EXECUTED
P8-REAL-EVIDENCE-POLICY                             NOT EXECUTED
P8-REAL-INJECTION-BOUNDARY                          NOT EXECUTED
P8 acceptance                                       NOT CLAIMED
```

## Permanent invariants

- Odoo remains persistence and operational authority.
- Business execution uses the effective user Environment with `su=False`.
- `CapabilityDefinition` remains the atomic executable contract.
- Skills, manifests, context and Evidence cannot create execution authority.
- Evidence is bounded untrusted data with host-owned provenance/access/freshness.
- Product-facing human profiles are User/non-technical and Technical only.
- A future host broker is an execution boundary, not a third human profile.
- Hidden, disabled or unauthorized capabilities remain non-executable.
- Approval is policy/autonomy-driven but never expands the user's Odoo authority.
- Full-control may reduce redundant approval only when trusted policy allows it.
- Effects remain preview/policy/approval-when-required/execute/verify operations.
- Ambiguous writes are not retried automatically.
- Arbitrary repositories may be candidates after bounded preflight; allowlist is optional policy/trust input.
- No arbitrary SQL, Python, shell, sudo or unrestricted ORM method is exposed.
- Raw/private provider reasoning, credentials and unsanitized payloads are not persisted or shown as public progress.
- User-pasted secrets do not automatically grant authority or require turn blocking; derived public projections must redact where possible.
- Optional extension failures are isolated; required providers fail closed.
- No unexecuted test or gate may be represented as PASS.

## Historical navigation

Current implementation/architecture:

```text
docs/CURRENT_STATE.md
docs/ARCHITECTURE.md
docs/CAPABILITY_FRAMEWORK.md
docs/PRODUCT_VISION.md
docs/research/P8_EVIDENCE_CORE_IMPLEMENTATION.md
docs/EVIDENCE_ARCHITECTURE.md
docs/OBSERVABILITY_ARCHITECTURE.md
docs/CONTEXT_SOURCE_POLICY.md
```

Completed preparation contract:

```text
docs/research/P8_EVIDENCE_CORE_PREPARATION.md
```

Older phase narratives and immutable proof remain in dated records under
`docs/research/evidence/`; they are not duplicated in this cursor and are excluded
from normal current-answer context by policy.
