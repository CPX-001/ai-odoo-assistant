# Stabilization execution state

State format: 61
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
P8 final acceptance through e370af8acb7df175c0a90c8e17520c8576b4c6ce
```

## Current cursor

```text
phase: 9
phase_name: company Knowledge/RAG and source lifecycle
active_slice: P9-FIRST-COHERENT-SLICE
slice_state: READY_TO_START
current_gate_type: P9_DESIGN_AND_FOCUSED_IMPLEMENTATION
blocking_implementation: none
blocking_validation: none from P8
latest_accepted_evidence: docs/research/evidence/phase8/2026-09-02/P8-ACCEPTANCE-e370af8.md
latest_phase_acceptance: docs/research/evidence/phase8/2026-09-02/P8-ACCEPTANCE-e370af8.md
next_action: reconstruct P9 from the active playbook and implement the largest coherent source-lifecycle, bounded-ingestion, lexical/FTS retrieval and chat-ingestion slice that can be validated together
```

## P8 acceptance result

```text
focused dependency-light                         PASS — 61 tests
focused Odoo + installed-addon fixture           PASS — 20 tests, 0 failures/errors
P8-REAL-SOURCE-DIAGNOSIS                         PASS
P8-REAL-LOG-DIAGNOSIS                            PASS
P8-REAL-PROVENANCE                               PASS
P8-REAL-FRESHNESS                                PASS
P8-REAL-EVIDENCE-POLICY                          PASS
P8-REAL-INJECTION-BOUNDARY                       PASS
effective Odoo user Environment                  PASS — su=False
P8 acceptance                                    COMPLETE / ACCEPTED
```

The authoritative command, environment, repair and rerun record is
`docs/research/evidence/phase8/2026-09-02/P8-ACCEPTANCE-e370af8.md`.

P8 added bounded installed-addon source/XML Evidence, correlated configured-log
Evidence, question-sensitive routing, logical locators, access/freshness checks,
secret redaction and browser-safe citation metadata on top of the provider-neutral
Evidence foundation. Retrieved text remains untrusted and cannot create execution
authority.

## Periodic validation debt and explicit limits

```text
full repository regression             NOT EXECUTED (periodic debt)
full addon regression                   NOT EXECUTED (periodic debt)
HOOT/browser regression                 NOT EXECUTED (periodic debt)
Product Behavior FULL                   NOT EXECUTED (periodic debt)
raw EvidenceLedger reconnect replay     NOT IMPLEMENTED / NOT A P8 ACCEPTANCE CLAIM
```

These broad suites were not required by the focused P8 runbook, and no focused
failure justified expanding the scope. Final citation metadata persists through the
normal result payload; richer raw-excerpt replay/navigation remains future work.

## Permanent invariants

- Odoo remains persistence and operational authority.
- Business execution uses the effective user Environment with `su=False`.
- `CapabilityDefinition` remains the atomic executable contract.
- Skills, manifests, context and Evidence cannot create execution authority.
- Evidence is bounded untrusted data with host-owned provenance/access/freshness.
- Product-facing human profiles are User/non-technical and Technical only; public values are `user` and `technical`.
- A future host broker is an execution boundary, not a third human profile.
- Hidden, disabled or unauthorized capabilities remain non-executable.
- Approval is policy/autonomy-driven but never expands the user's Odoo authority.
- Effects remain preview/policy/approval-when-required/execute/verify operations.
- Ambiguous writes are not retried automatically.
- No arbitrary SQL, Python, shell, sudo or unrestricted ORM method is exposed.
- Raw/private provider reasoning, credentials and unsanitized payloads are not persisted or shown as public progress.
- User-pasted secrets do not automatically grant authority; derived public projections redact where possible.
- Optional extension failures are isolated; required providers fail closed.
- No unexecuted test or gate may be represented as PASS.

## Historical navigation

Current architecture and implementation records:

```text
docs/CURRENT_STATE.md
docs/ARCHITECTURE.md
docs/CAPABILITY_FRAMEWORK.md
docs/EVIDENCE_ARCHITECTURE.md
docs/OBSERVABILITY_ARCHITECTURE.md
docs/CONTEXT_SOURCE_POLICY.md
docs/research/P8_EVIDENCE_CORE_IMPLEMENTATION.md
docs/research/P8_FOCUSED_VALIDATION_RUNBOOK.md
```

Older phase narratives and immutable proof remain under `docs/research/evidence/`;
they are historical evidence rather than the current execution cursor.
