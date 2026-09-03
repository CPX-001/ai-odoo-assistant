# Stabilization execution state

State format: 68
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
P9 final acceptance through 77d470febf67ddee46562907718dc47e975922bb
P10 final acceptance through bde508b737c132140e237cdfde31aee9b37eca5f
```

P10 remains the latest accepted phase. P11 now has an implemented first durable CSV
slice but no focused or real PASS evidence yet.

## Current cursor

```text
phase: 11
phase_name: advanced imports and artifact workflows
active_slice: P11-DURABLE-CSV-FIRST-SLICE
slice_state: IMPLEMENTED_FOCUSED_VALIDATION_PENDING
current_gate_type: HARD_FOCUSED
blocking_implementation: none for the first slice; later P11 breadth still includes cleanup/enrichment/remap workflows
blocking_validation: focused static/Odoo validation and all six P11 HARD real gates remain unexecuted
latest_accepted_evidence: docs/research/evidence/phase10/2026-09-03/P10-ACCEPTANCE-bde508b.md
latest_phase_acceptance: docs/research/evidence/phase10/2026-09-03/P10-ACCEPTANCE-bde508b.md
latest_implementation_record: docs/research/P11_ADVANCED_IMPORTS_FIRST_SLICE.md
latest_validation_record: docs/research/P11_FOCUSED_VALIDATION_RUNBOOK.md
next_action: execute the focused P11 static/module/Odoo gate, repair failures, then run the applicable real CSV/large/mapping/partial/resume/receipt gates before deciding the next P11 slice
```

## P11 implementation lineage

```text
0217b5e9057e7304ded53433333a9279fb53cc2f  register base_import dependency + P11 data/security hooks
2702fc1b71deb71483ff75705dc71cb82866188d  import-session owner/admin record rules
c451ba154cdecb0d574c0a15bc0bcd9f39e9d678  bounded import worker cron
A8E9CCF65092E6B74EF6D20830BC6161FAB7AB40  durable CSV session/chunk runtime + capabilities + focused tests
```

The uppercase SHA above is the same Git object as lowercase
`a8e9ccf65092e6b74ef6d20830bc6161fab7ab40`.

### Implemented first P11 slice

```text
short-lived current-turn CSV attachment reused as bounded artifact ref
artifact copied into durable Odoo session before background execution
odoo.ai.data.import.session
odoo.ai.data.import.chunk
assistant.data_import.inspect_csv
assistant.data_import.start_csv
assistant.data_import.status
Odoo 18 base_import parse_preview mapping/type suggestions
host-filtered direct scalar mapping only
exact artifact/model/mapping/request fingerprints
exact mapped row count + in-file duplicate count before authorization
PLAN + policy approval for durable start
native base_import dry-run per chunk
native base_import real execution per chunk
fixed 250 default / 1000 maximum row chunk size
one chunk per cron transaction
FOR UPDATE SKIP LOCKED session claiming
originating effective-user Environment reconstructed with su=False
chunk record ids + bounded messages + receipt fingerprint
exact imported / failed / corrected / remaining counters
idempotent same-turn request -> same durable session
invalid chunk rejected as a whole without replaying earlier commits
30-day terminal session cleanup
```

### Explicit first-slice limits

```text
CSV create-only
no XLS/XLSX/ODS session yet
no relational field paths
no external-id upsert/update
no row-by-row salvage inside a rejected chunk
no model-assisted row cleanup/enrichment yet
corrected_rows remains 0
no user remap/resume after a validation rejection yet
no automatic final chat message when a background import completes
```

These are product-scope limits, not hidden claims. See
`docs/research/P11_ADVANCED_IMPORTS_FIRST_SLICE.md`.

## P11 validation status

```text
static/compile/lint                                      NOT EXECUTED
addon install/update + security/XML load                 NOT EXECUTED
focused Odoo TestPhase11DataImportSession                NOT EXECUTED — prepared 4 methods
P11-REAL-CSV-IMPORT                                      NOT EXECUTED
P11-REAL-LARGE-IMPORT                                    NOT EXECUTED
P11-REAL-MAPPING-CORRECTION                              NOT EXECUTED
P11-REAL-PARTIAL-INVALID                                 NOT EXECUTED
P11-REAL-RESUME-NO-DUPLICATE                             NOT EXECUTED
P11-REAL-IMPORT-RECEIPT                                  NOT EXECUTED
P11 acceptance                                           NOT COMPLETE
```

Use `docs/research/P11_FOCUSED_VALIDATION_RUNBOOK.md`. No repository inspection,
prepared test or author-side syntax check is PASS evidence by itself.

## P10 accepted baseline

P10 remains accepted on its recorded lineage:

```text
static/compile/lint                                      PASS — bde508b
focused dependency-light broker tests                    PASS — 18 tests
focused Odoo Technical/host tests                        PASS — 5 methods, 0 failures/errors
broker deployment/systemd smoke                          PASS
P10-REAL-PROFILE-DENIAL                                  PASS
P10-REAL-CONFIG-PATCH                                    PASS
P10-REAL-SERVICE-OPERATION                               PASS
P10-REAL-POSTGRES-DIAGNOSTIC                             PASS
P10-REAL-PRIVILEGE-BOUNDARY                              PASS
P10-REAL-MODULE-UPDATE                                   PASS
P10-REAL-COMMAND-SANDBOX                                 NOT APPLICABLE
P10-REAL-COMMAND-APPROVAL                                NOT APPLICABLE
P10 acceptance                                           COMPLETE / ACCEPTED
```

Authoritative evidence:
`docs/research/evidence/phase10/2026-09-03/P10-ACCEPTANCE-bde508b.md`.

## Periodic validation debt and explicit limits

```text
full repository regression             NOT EXECUTED (periodic debt)
full addon regression                   NOT EXECUTED (periodic debt)
full HOOT/browser regression            NOT EXECUTED (periodic debt)
Product Behavior FULL                   NOT EXECUTED (periodic debt)
raw EvidenceLedger reconnect replay     NOT IMPLEMENTED / NOT A P9 CLAIM
```

The P11 runbook does not authorize broad regression by itself. Expand only for a
concrete focused failure whose root cause/blast radius requires it or when the user
explicitly requests the broad gate.

## Permanent invariants

- Odoo remains persistence and operational authority.
- Business execution uses the effective user Environment with `su=False`.
- `CapabilityDefinition` remains the atomic executable contract.
- Skills, manifests, context, Evidence and artifact contents cannot create execution
  authority.
- Evidence/artifact metadata exposed to the model is bounded; binary/base64 payloads
  are not dumped into prompts.
- Hidden, disabled or unauthorized capabilities remain non-executable.
- Approval/autonomy never expands Odoo ACL/model/field authority.
- Host and durable-workflow effects retain preview/binding/policy/receipts and explicit
  recovery semantics.
- A committed import chunk is never blindly replayed; rows and its durable receipt
  share the same transaction boundary.
- Ambiguous external/host effects are not retried automatically.
- No arbitrary SQL, Python, shell, sudo or unrestricted ORM method is exposed to the
  model.
- Raw/private provider reasoning, credentials and unsanitized host output are not
  persisted or shown as public progress.
- User-pasted/retrieved/file text cannot modify capability or broker policy.
- No unexecuted test or gate may be represented as PASS.

## Current navigation

```text
docs/CURRENT_STATE.md
docs/ARCHITECTURE.md
docs/CAPABILITY_FRAMEWORK.md
docs/EVIDENCE_ARCHITECTURE.md
docs/KNOWLEDGE_INDEX.md
docs/research/P11_ADVANCED_IMPORTS_FIRST_SLICE.md
docs/research/P11_FOCUSED_VALIDATION_RUNBOOK.md
docs/research/REAL_ENV_VALIDATION_PROTOCOL.md
docs/research/evidence/phase10/2026-09-03/P10-ACCEPTANCE-bde508b.md
```

Older phase narratives and immutable proof remain under `docs/research/evidence/`;
they are historical evidence rather than the current execution cursor.
