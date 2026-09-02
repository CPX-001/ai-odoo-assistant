# Stabilization execution state

State format: 63
Updated: 2026-09-03

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
slice_state: FOCUSED_PASS_REAL_VALIDATION_BLOCKED
current_gate_type: P9_REAL_VALIDATION
blocking_implementation: none known after focused validation and browser repair
blocking_validation: primary host CODEX_HOME requires reauthentication; the first provider-backed gate failed closed with codex_turn_failed / authentication / unauthorized
latest_accepted_evidence: docs/research/evidence/phase8/2026-09-02/P8-ACCEPTANCE-e370af8.md
latest_phase_acceptance: docs/research/evidence/phase8/2026-09-02/P8-ACCEPTANCE-e370af8.md
latest_implementation_record: docs/research/P9_KNOWLEDGE_FIRST_SLICE.md
latest_validation_record: docs/research/evidence/phase9/2026-09-03/P9-VALIDATION-BLOCKED-e227da1.md
next_action: reauthenticate the normal primary host Codex session in /home/cpx/.codex, then rerun tests/e2e/p9_real_knowledge_gate.py against e227da1; accept P9 and move the cursor to P10 only if all seven real gates pass
```

## P9 first-slice implementation state

Implemented on main but not yet validated in an execution environment:

```text
Odoo-native Knowledge source/chunk/temporary-attachment models
uploaded -> processing -> indexed/active | error lifecycle
bounded deterministic TXT/Markdown/RST/CSV/JSON/XML ingestion
PostgreSQL lexical/FTS search with GIN expression index
assistant.company_knowledge EvidenceProvider
Knowledge-aware question-sensitive Evidence routing
version/fingerprint freshness revalidation and browser-safe citation metadata
company/private Odoo record-rule boundaries
host-owned derived chunk mutation
bounded temporary Assistant attachment transport
retry-safe attachment -> durable turn binding
assistant.knowledge.ingest_attachment capability with preview + verification
Assistant composer attachment chip/control
focused Odoo/unit coverage prepared
real Odoo/Codex P9 gate runner prepared
```

The implementation deliberately does not add PDF/OCR parsing, embeddings/vector
storage or a second RAG runtime. Those remain conditional future P9 work, not missing
requirements for this first lexical slice.

## P9 validation status

```text
static/compile/lint                            PASS
focused dependency-light                      PASS — 49 tests
focused Odoo                                  PASS — 25 tests, 0 failures/errors
focused HOOT                                  PASS — 1 test / 1 assertion
focused browser/asset smoke                    PASS after attachment-marker repair
P9-REAL-UPLOAD-INGEST                         PASS
P9-REAL-CHAT-INGEST                           BLOCKED / NOT EXECUTED
P9-REAL-FTS                                   BLOCKED / NOT EXECUTED
P9-REAL-CITATIONS                             BLOCKED / NOT EXECUTED
P9-REAL-ACL                                   BLOCKED / NOT EXECUTED
P9-REAL-REINDEX                               BLOCKED / NOT EXECUTED
P9-REAL-LARGE-DOCUMENT                        BLOCKED / NOT EXECUTED
P9-REAL-SEMANTIC-GAIN                         NOT APPLICABLE unless vector backend is introduced
P9 acceptance                                 NOT CLAIMED — P10 NOT YET ELIGIBLE
```

The exact commands, focused repair and provider-authentication failure are recorded in
`docs/research/evidence/phase9/2026-09-03/P9-VALIDATION-BLOCKED-e227da1.md`.

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

The authoritative P8 command, environment, repair and rerun record is
`docs/research/evidence/phase8/2026-09-02/P8-ACCEPTANCE-e370af8.md`.

## Periodic validation debt and explicit limits

```text
full repository regression             NOT EXECUTED (periodic debt)
full addon regression                   NOT EXECUTED (periodic debt)
full HOOT/browser regression            NOT EXECUTED (periodic debt)
Product Behavior FULL                   NOT EXECUTED (periodic debt)
raw EvidenceLedger reconnect replay     NOT IMPLEMENTED / NOT A P9 CLAIM
```

The focused P9 browser smoke is blocking because this slice changes the composer;
the full browser regression remains periodic unless focused failures widen the blast
radius.

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
docs/KNOWLEDGE_INDEX.md
docs/OBSERVABILITY_ARCHITECTURE.md
docs/CONTEXT_SOURCE_POLICY.md
docs/research/P8_EVIDENCE_CORE_IMPLEMENTATION.md
docs/research/P8_FOCUSED_VALIDATION_RUNBOOK.md
docs/research/P9_KNOWLEDGE_FIRST_SLICE.md
docs/research/P9_FOCUSED_VALIDATION_RUNBOOK.md
```

Older phase narratives and immutable proof remain under `docs/research/evidence/`;
they are historical evidence rather than the current execution cursor.
