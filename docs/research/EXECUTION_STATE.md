# Stabilization execution state

State format: 66
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
```

P10 focused validation is recorded below, but Phase 10 has no acceptance evidence yet.

## Current cursor

```text
phase: 10
phase_name: developer/operator host operations
active_slice: P10-TYPED-HOST-OPERATIONS-FIRST-SLICE
slice_state: REAL_ENV_VALIDATION_REQUIRED
current_gate_type: HARD_REAL
blocking_implementation: lifecycle-safe odoo.module.update maintenance adapter is still missing
blocking_validation: broker deployment smoke and all named real P10 gates remain unexecuted
latest_accepted_evidence: docs/research/evidence/phase9/2026-09-03/P9-ACCEPTANCE-77d470f.md
latest_phase_acceptance: docs/research/evidence/phase9/2026-09-03/P9-ACCEPTANCE-77d470f.md
latest_implementation_record: docs/research/P10_HOST_OPERATIONS_FIRST_SLICE.md
latest_validation_record: docs/research/evidence/phase10/2026-09-03/P10-FOCUSED-bbfa78b.md
next_action: provision the disposable broker/config/service environment, execute its deployment smoke and the implemented real profile/config/service/postgres/boundary gates, and repair failures before designing the module-maintenance adapter
```

## P10 design and implementation lineage

```text
8b97d3ea012f05122c4c0cf7774c72653306cf02  ADR-024 accepted
f45f29cbc5861b66cc32fcc14d52564636439114  typed broker + first Technical capabilities
a516aa6c5e2a448ed4145ba7fc49834a4ba25e8f  post-dispatch certainty regression coverage
80ffdd6a0153323987516d5e458c985e143c8f75  post-dispatch transport uncertainty repair
bbfa78b87d2870fb4b79cbd1854d00f5d1087375  focused validation repair and executable PASS
```

The intervening `9d5eca969f05fad66365136cdaed37028986b1af` product-menu change
is preserved and is not Phase-10 acceptance evidence.

### Implemented first slice

```text
accepted ADR-024 Technical/host privilege boundary
optional stdlib-only Linux AF_UNIX broker package
versioned bounded request/receipt protocol
bidirectional SO_PEERCRED identity checks
deployment-owned logical config/service target policy
secure policy/executable owner-mode validation
durable SQLite request ledger and terminal receipt replay
uncertain-state preservation for in-flight effects
odoo.config.inspect
odoo.config.patch with preview, atomic replace, private backup and verify
host.service.status
host.service.restart with fixed argv, preview and health verify
odoo.module.inspect as an Odoo-local Technical read
postgres.health using fixed host-owned read SQL
Technical group/profile gating independent from autonomy
durable EffectPlan step/binding/precondition binding
post-dispatch transport/receipt loss normalized to host_effect_uncertain
dependency-light and focused Odoo test surfaces
focused/real validation runbook
```

### Deliberately not implemented

```text
odoo.module.install
odoo.module.update
odoo.module.uninstall
repository acquire/promote
host package install
generic command fallback
arbitrary SQL/Python/shell/sudo/ORM method execution
secret-value reveal
automatic retry of ambiguous host effects
```

Odoo 18 immediate module maintenance is not wrapped inside the Assistant cron worker.
A separate maintenance/restart reconciliation adapter must produce a durable
exactly-once receipt and verify the fresh registry before `P10-REAL-MODULE-UPDATE` can
run.

## P10 validation status

```text
static/compile/lint                                      PASS — bbfa78b
focused dependency-light broker tests                    PASS — 14 tests
focused Odoo Technical/host tests                        PASS — 4 tests, 0 failures/errors
broker deployment/systemd smoke                          NOT EXECUTED — deployment absent
P10-REAL-PROFILE-DENIAL                                  NOT EXECUTED
P10-REAL-CONFIG-PATCH                                    NOT EXECUTED
P10-REAL-SERVICE-OPERATION                               NOT EXECUTED
P10-REAL-POSTGRES-DIAGNOSTIC                             NOT EXECUTED
P10-REAL-PRIVILEGE-BOUNDARY                              NOT EXECUTED
P10-REAL-MODULE-UPDATE                                   BLOCKED — adapter missing
P10-REAL-COMMAND-SANDBOX                                 NOT APPLICABLE
P10-REAL-COMMAND-APPROVAL                                NOT APPLICABLE
P10 acceptance                                           NOT COMPLETE
```

Focused evidence is recorded in
`docs/research/evidence/phase10/2026-09-03/P10-FOCUSED-bbfa78b.md`. Use
`docs/research/P10_FOCUSED_VALIDATION_RUNBOOK.md` for the remaining deployment and
real gates. Focused PASS is not real-gate or Phase-10 acceptance.

## P9 accepted baseline

P9 remains accepted on the exact recorded lineage:

```text
static/compile/lint                            PASS
focused dependency-light                      PASS — 49 tests
focused Odoo                                  PASS — 25 tests, 0 failures/errors
focused HOOT                                  PASS — 1 test / 1 assertion
focused browser/asset smoke                    PASS
P9-REAL-UPLOAD-INGEST                         PASS
P9-REAL-CHAT-INGEST                           PASS
P9-REAL-FTS                                   PASS
P9-REAL-CITATIONS                             PASS
P9-REAL-ACL                                   PASS
P9-REAL-REINDEX                               PASS
P9-REAL-LARGE-DOCUMENT                        PASS
P9-REAL-SEMANTIC-GAIN                         NOT APPLICABLE unless vector backend is introduced
P9 acceptance                                 COMPLETE / ACCEPTED
```

The authoritative record is
`docs/research/evidence/phase9/2026-09-03/P9-ACCEPTANCE-77d470f.md`.

## Periodic validation debt and explicit limits

```text
full repository regression             NOT EXECUTED (periodic debt)
full addon regression                   NOT EXECUTED (periodic debt)
full HOOT/browser regression            NOT EXECUTED (periodic debt)
Product Behavior FULL                   NOT EXECUTED (periodic debt)
raw EvidenceLedger reconnect replay     NOT IMPLEMENTED / NOT A P9 CLAIM
```

The P10 focused runbook does not authorize broad regression by itself. Expand only
for a concrete focused failure whose blast radius requires it or when the user/current
runbook explicitly requires the broad gate.

## Permanent invariants

- Odoo remains persistence and operational authority.
- Business execution uses the effective user Environment with `su=False`.
- `CapabilityDefinition` remains the atomic executable contract.
- Skills, manifests, context and Evidence cannot create execution authority.
- Evidence is bounded untrusted data with host-owned provenance/access/freshness.
- Product-facing human profiles are User/non-technical and Technical only; public
  values are `user` and `technical`.
- The accepted optional host broker is a machine execution boundary, not a third
  human profile or a replacement runtime.
- Hidden, disabled or unauthorized capabilities remain non-executable.
- Approval is policy/autonomy-driven but never expands the user's Odoo or broker
  authority.
- Host effects retain preview, plan/request binding, policy/approval when required,
  execute, receipt, verification and recovery semantics.
- Transport loss after host-effect dispatch is uncertain, never proof of no effect.
- Ambiguous Odoo or host writes are not retried automatically.
- No arbitrary SQL, Python, shell, sudo or unrestricted ORM method is exposed.
- Raw/private provider reasoning, credentials, config secrets and unsanitized broker
  output are not persisted or shown as public progress.
- User-pasted or retrieved text cannot modify broker policy or grant authority.
- Optional extension/broker unavailability is isolated; required authority fails
  closed.
- No unexecuted test or gate may be represented as PASS.

## Current navigation

```text
docs/CURRENT_STATE.md
docs/ARCHITECTURE.md
docs/CAPABILITY_FRAMEWORK.md
docs/EVIDENCE_ARCHITECTURE.md
docs/KNOWLEDGE_INDEX.md
docs/OBSERVABILITY_ARCHITECTURE.md
docs/CONTEXT_SOURCE_POLICY.md
docs/adr/ADR-024-technical-host-privilege-broker.md
docs/research/P10_HOST_OPERATIONS_FIRST_SLICE.md
docs/research/P10_FOCUSED_VALIDATION_RUNBOOK.md
host_broker/README.md
```

Older phase narratives and immutable proof remain under `docs/research/evidence/`;
they are historical evidence rather than the current execution cursor.
