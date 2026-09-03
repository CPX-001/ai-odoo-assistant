# Stabilization execution state

State format: 70
Updated: 2026-09-03

## Accepted lineage

```text
P0-P4 through 8a4432dc9852eacc422b8c794b6613c75da702a9
P5.1-P5.8 accepted on their recorded evidence
P6 final acceptance through 0b1bcab39b71dfbe02526cda7cf7ac8e218ac4b0
P7 final acceptance through 092ac57fe58a3a36765b115e78b2eca687f5dbbc
P8 final acceptance through e370af8acb7df175c0a90c8e17520c8576b4c6ce
P9 final acceptance through 77d470febf67ddee46562907718dc47e975922bb
P10 final acceptance through bde508b737c132140e237cdfde31aee9b37eca5f
P11 final acceptance through 72b4b826bddffc20f99f5cd72f14ed95111eab5c
```

P11 is the latest accepted phase. P12 is eligible but has no implementation or PASS
claim yet.

## Current cursor

```text
phase: 12
phase_name: controlled source-code modification
active_slice: P12.1-BOUNDED-WORKSPACE-SOURCE-ROOTS
slice_state: READY_NOT_STARTED
current_gate_type: HARD_AUTHORITY_AND_DESIGN
blocking_implementation: P12 has not started; no source-edit capability, patch/deploy path or new privilege grant exists
blocking_validation: none for entering P12; every P12 implementation slice must define and pass its own focused gates before the five named real gates
latest_accepted_evidence: docs/research/evidence/phase11/2026-09-03/P11-ACCEPTANCE-72b4b82.md
latest_phase_acceptance: docs/research/evidence/phase11/2026-09-03/P11-ACCEPTANCE-72b4b82.md
latest_implementation_record: docs/research/P11_IMPORT_CLEANUP_REPAIR_SLICE.md
latest_validation_record: docs/research/evidence/phase11/2026-09-03/P11-ACCEPTANCE-72b4b82.md
next_action: begin P12.1 by specifying bounded workspace/source roots, identities, fingerprints and the no-production-mutation privilege boundary before exposing any source-edit capability
```

## P11 implementation lineage

```text
0217b5e9057e7304ded53433333a9279fb53cc2f  base_import dependency + P11 data/security hooks
2702fc1b71deb71483ff75705dc71cb82866188d  import-session owner/admin record rules
c451ba154cdecb0d574c0a15bc0bcd9f39e9d678  bounded import worker cron
a8e9ccf65092e6b74ef6d20830bc6161fab7ab40  durable CSV session/chunk runtime + first capabilities/tests
4910e42cd60ad2786b831259c188aa19e946082a  stage mapped rows once for bounded chunk execution
cf40ed2946b1347b2ba2aefb8047030a5799e5b2  deterministic cleanup + rejected-window repair session logic
a0868240865b508426c949d10a1299f41236771a  cleanup/repair capability surface
98e086b28e584cb374caf2b5b6308c70cd8297f5  register cleanup/repair model extension
f750c76352c3ccbce3420475325295bd2cb4aaec  focused cleanup/repair tests
866e956ba793426b71fddf3b7730320705fc9d41  register focused repair test class
2ff209c9f7dc9ccd8ec1729ac2d04e6ceb587714  addon version 18.0.13.30.0
36d52ec07cd48a1402a0730502ff641e10407d07  validation repairs: persisted mapping, nullable empty receipts and flushed worker claim
72b4b826bddffc20f99f5cd72f14ed95111eab5c  reproducible real Odoo/Codex P11 gate runner
```

## Implemented P11 core

```text
bounded current-turn CSV artifact reference
artifact copied into durable Odoo session
odoo.ai.data.import.session
odoo.ai.data.import.chunk
Odoo 18 base_import preview/type/mapping suggestions
host-filtered direct scalar create mapping
mapped rows staged once with bounded size/chunk-count ceilings
exact artifact/model/mapping/prepared-row/request fingerprints
exact row count + in-file duplicate count before authorization
250 default / 1000 maximum rows per chunk
one bounded chunk per cron transaction
FOR UPDATE SKIP LOCKED claiming on Assistant-owned session table
effective-user target writes with su=False
per-chunk record ids, sanitized messages and receipt fingerprint
committed rows + cursor + completed receipt share the same transaction
whole-chunk rollback/rejected receipt for native import errors
idempotent same-turn start
30-day terminal cleanup
```

Capability surface:

```text
assistant.data_import.inspect_csv       READ
assistant.data_import.start_csv         PLAN / ACTION / POLICY
assistant.data_import.status            READ
assistant.data_import.inspect_cleanup   READ
assistant.data_import.start_clean_csv   PLAN / ACTION / POLICY
assistant.data_import.inspect_rejected  READ
assistant.data_import.resume_csv        PLAN / ACTION / POLICY
```

Cleanup/repair semantics:

```text
finite cleanup rules: trim / normalize_whitespace / replace_exact / set_if_empty
cleanup restricted to fields already in the validated mapping
exact changed-row + duplicate before/after preview
corrected_rows counts only changed rows that actually commit
bounded rejected-window inspection under owner/company binding
explicit row + mapped-field + replacement repair only
repair revision + fingerprint bound to rejected receipt and staged before/after state
next_row remains at the last committed cursor during repair
historical rejected receipt is retained
new repaired attempt receives a new receipt sequence
failed_rows represents unresolved rejected rows and can return to zero after successful repair
completed chunks are never replayed by repair/resume
```

## Explicit P11 breadth limits

```text
CSV create-only
no XLS/XLSX/ODS durable session yet
no relational field paths
no external-id update/upsert
no arbitrary expression/script transformation language
no generic semantic matching against existing business records
no automatic background completion turn/message yet
```

These are explicit scope boundaries, not hidden claims. The current safe CSV core is
intended to satisfy the P11 product goal unless real HARD gates demonstrate that one
of these broader features is required.

## P11 validation and acceptance

```text
static/compile/lint                                      PASS
addon install/update + security/XML/model load           PASS
focused TestPhase11DataImportSession                     PASS — 4 methods
focused TestPhase11DataImportCleanupRepair               PASS — 4 methods
P11-REAL-CSV-IMPORT                                      PASS
P11-REAL-LARGE-IMPORT                                    PASS — 1,200 rows / 6 x 200
P11-REAL-MAPPING-CORRECTION                              PASS
P11-REAL-PARTIAL-INVALID                                 PASS
P11-REAL-RESUME-NO-DUPLICATE                             PASS
P11-REAL-IMPORT-RECEIPT                                  PASS
P11 acceptance                                           COMPLETE / P12 ELIGIBLE
```

Immutable execution detail is in
`docs/research/evidence/phase11/2026-09-03/P11-ACCEPTANCE-72b4b82.md`. The checked-in
real runner is `tests/e2e/p11_real_import_gate.py`.

## P11 accepted baseline

P11 is accepted on the immutable evidence at:

`docs/research/evidence/phase11/2026-09-03/P11-ACCEPTANCE-72b4b82.md`

P10 remains accepted at its earlier evidence anchor. P11 validation covered the exact
focused Odoo classes plus all six mandatory real attached-file/import/recovery gates.
The explicit CSV create-only breadth boundary remains in force.

## Periodic validation debt

```text
full repository regression             NOT EXECUTED (periodic debt)
full addon regression                   NOT EXECUTED (periodic debt)
full HOOT/browser regression            NOT EXECUTED (periodic debt)
Product Behavior FULL                   NOT EXECUTED (periodic debt)
raw EvidenceLedger reconnect replay     NOT IMPLEMENTED / NOT A P9 CLAIM
```

The P11 runbook does not authorize those broad suites automatically.

## Permanent invariants

- Odoo remains persistence and operational authority.
- Business execution uses the effective user Environment with `su=False`.
- `CapabilityDefinition` remains the atomic executable contract.
- Skills, manifests, context, Evidence and artifact contents cannot grant authority.
- Binary/base64 and complete staged tables are not dumped into model prompts.
- Approval/autonomy never expands Odoo model/record/field authority.
- Durable workflow effects retain preview, binding, policy, receipt and recovery
  semantics.
- A committed import chunk is never blindly replayed.
- Cleanup/repair can alter only already-mapped staged values through finite host-owned
  operations; it cannot create a new model/field/tool authority surface.
- Ambiguous external/host effects are not retried automatically.
- No arbitrary SQL, Python, shell, sudo or unrestricted ORM method is exposed.
- Raw/private provider reasoning, credentials and unsanitized host output are not
  persisted or shown as public progress.
- No unexecuted test or gate may be represented as PASS.

## Current navigation

```text
docs/CURRENT_STATE.md
docs/ARCHITECTURE.md
docs/CAPABILITY_FRAMEWORK.md
docs/EVIDENCE_ARCHITECTURE.md
docs/KNOWLEDGE_INDEX.md
docs/research/P11_ADVANCED_IMPORTS_FIRST_SLICE.md
docs/research/P11_IMPORT_CLEANUP_REPAIR_SLICE.md
docs/research/P11_FOCUSED_VALIDATION_RUNBOOK.md
docs/research/REAL_ENV_VALIDATION_PROTOCOL.md
docs/research/evidence/phase11/2026-09-03/P11-ACCEPTANCE-72b4b82.md
docs/research/AGENTIC_PRODUCT_EVOLUTION_PLAYBOOK.md#phase-12
```

Older phase narratives and immutable proof remain historical evidence rather than the
current execution cursor.
