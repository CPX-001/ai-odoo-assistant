# Current implementation state

This is the current-state entry point for the supported Odoo 18 product on `main`.
For the exact roadmap cursor, latest accepted evidence and unexecuted gates, use
[`research/EXECUTION_STATE.md`](research/EXECUTION_STATE.md).

## Accepted lineage

```text
P0-P4 accepted
P5.1-P5.8 accepted
P6 COMPLETE / ACCEPTED
P7 COMPLETE / ACCEPTED at 092ac57fe58a3a36765b115e78b2eca687f5dbbc
P8 COMPLETE / ACCEPTED at e370af8acb7df175c0a90c8e17520c8576b4c6ce
P9 COMPLETE / ACCEPTED at 77d470febf67ddee46562907718dc47e975922bb
P10 COMPLETE / ACCEPTED at bde508b737c132140e237cdfde31aee9b37eca5f
P11 FIRST DURABLE CSV SLICE IMPLEMENTED / VALIDATION PENDING
```

P10 remains the latest accepted phase. Its evidence is
`research/evidence/phase10/2026-09-03/P10-ACCEPTANCE-bde508b.md`.
P11 is not accepted yet; implementation or prepared tests are not PASS evidence.

Current P11 records:

```text
research/P11_ADVANCED_IMPORTS_FIRST_SLICE.md
research/P11_FOCUSED_VALIDATION_RUNBOOK.md
```

## 1. Product and deployment baseline

- Target: Odoo 18 Community, self-hosted Linux.
- Supported addon: `addons/odoo_ai_assistant`.
- Current addon manifest version: `18.0.13.28.0`.
- Current dependencies: `account`, `base`, `base_import`, `sale`, `web`.
- Runtime is embedded in Odoo; the browser talks only to authenticated Odoo routes.
- Odoo/PostgreSQL own conversations, turns, queue, effects, recovery, Evidence,
  Knowledge and durable import-session state.
- Long turns, Knowledge ingestion and P11 import chunks use native `ir.cron` workers.
- Business operations run as the effective Odoo user with `su=False`.
- Codex App Server is the current concrete reasoning provider and remains an
  ephemeral/provider-owned subprocess.
- The addon is an Odoo application for Knowledge, Diagnostics and Configuration;
  chat remains globally available from the systray.
- The retired FastAPI/Uvicorn Assistant sidecar is not part of the supported product.

The optional P10 host broker is a separate finite machine-privilege adapter. It is not
the Assistant runtime and does not own conversation, turn or P11 import state.

## 2. Authority and effect model

The reasoning provider proposes. Odoo/host code remains authoritative for:

```text
user / companies / groups
ACL / record rules / field access
capability identity + schema + availability
provider / Skill / Context / Evidence composition
budgets
policy / autonomy / approval
EffectPlan preparation and binding
write barrier / execution
verification / recovery / receipts
public progress projection
Evidence access / freshness / trust
Knowledge ownership / indexing lifecycle
artifact/model/mapping validation
P11 durable import cursor + chunk receipts
```

`CapabilityDefinition` remains the atomic executable unit. There is no arbitrary SQL,
Python, shell, sudo or unrestricted ORM-method escape hatch. Fixed host-owned SQL may
be used internally for bounded infrastructure such as queue claiming; it is never a
model-authored SQL surface.

Effects use:

```text
discover / resolve
 -> inspect schema and preconditions
 -> prepare / preview
 -> policy
 -> approval when required
 -> durable write barrier
 -> execute
 -> verify
 -> receipt / recovery
```

Approval is policy/autonomy-driven but never enlarges Odoo, field or broker authority.
Ambiguous effects are not blindly retried.

## 3. Durable agent runtime

The accepted P5/P6 runtime remains current:

- durable conversations and `odoo.ai.turn`;
- queue, lease, cancellation and stale recovery;
- one active causal turn per conversation with cross-conversation concurrency;
- provider-neutral `NextDecision` loop;
- public bounded TaskPlan and separate typed EffectPlan;
- bounded query, batch and workflow capabilities;
- EffectJournal and recovery-unit semantics;
- stop, corrections and interventions;
- public activity, answer deltas and final reconciliation;
- immutable per-turn model/reasoning/autonomy/planning settings;
- bounded exact resource references from verified effects for natural follow-ups;
- structured prepare/preflight/execution failure feedback;
- no replay of a completed or uncertain effect.

P7-P11 extend this embedded runtime rather than adding another general agent service or
database.

## 4. Extension framework and profiles

The live framework includes `CapabilityProvider`, Skills, ContextProviders,
EvidenceProviders, `ProviderProfile`, `EffectiveAssistantManifest`, installed-addon
provider discovery, optional-provider isolation and progressive disclosure.
Every executable operation still resolves through the same registry, executor, policy
and effective user.

Product-facing profiles are exactly:

```text
user
technical
```

Autonomy is independent from technical reach.

## 5. Evidence and installation intelligence — accepted P8

The shared Evidence layer is bounded, provenance-aware, freshness-aware, ACL-aware and
non-executable. Current providers cover runtime inventory, installed-addon source/XML
and configured logs. Retrieved text is untrusted data and cannot grant authority.

## 6. Company Knowledge — accepted P9

P9 provides:

```text
odoo.ai.knowledge.source
odoo.ai.knowledge.chunk
odoo.ai.knowledge.attachment
assistant.company_knowledge
assistant.knowledge.ingest_attachment
```

Knowledge handles bounded PDF/TXT/Markdown/RST/CSV/JSON/XML ingestion and PostgreSQL
lexical FTS with current ACL/provenance/fingerprint semantics. Chat attachments are
short-lived current-turn artifacts until an authorized capability persists them.
Embeddings/vector retrieval remain conditional on measured gain.

## 7. Technical and host operations — accepted P10

P10 provides Technical-only local reads and optional broker-backed operations:

```text
odoo.module.inspect
postgres.health
odoo.config.inspect
odoo.config.patch
host.service.status
host.service.restart
odoo.module.update
```

ADR-024 owns the privilege boundary: exact deployment logical targets, `SO_PEERCRED`,
fixed argv, bounded request/receipt schemas, durable replay ledger, precondition/effect
binding and explicit uncertain-state handling. Module update runs through the accepted
external maintenance adapter rather than immediate upgrade inside the Assistant cron
worker.

Not implemented by P10: module install/uninstall, repository/package promotion,
generic shell fallback, secret reveal or arbitrary SQL/Python/sudo.

## 8. Advanced imports/artifacts — P11 first slice implemented

P11 now has a first durable create-only CSV workflow. It deliberately does not turn a
large file into hundreds or thousands of ordinary CRUD tool calls.

New durable models:

```text
odoo.ai.data.import.session
odoo.ai.data.import.chunk
```

New capabilities:

```text
assistant.data_import.inspect_csv   READ
assistant.data_import.start_csv     PLAN / policy-controlled effect
assistant.data_import.status        READ
```

The flow is currently:

```text
current-turn CSV attachment
 -> Odoo-native base_import preview / type + mapping suggestions
 -> host-filter target model and direct writable scalar fields
 -> explicit model-proposed column_index -> field map
 -> host revalidation + artifact/model/mapping/row fingerprints
 -> preview / policy / approval
 -> durable import session
 -> bounded background chunks under originating user, su=False
 -> per-chunk created-record ids + receipt fingerprint
 -> exact imported / rejected / remaining counters
```

The session copies the binary attachment before background execution, so expiry of the
short-lived chat upload does not destroy queued work. The model only receives bounded
artifact metadata/examples, not binary/base64 payloads.

Current field scope is intentionally direct scalar create fields only:

```text
boolean / char / date / datetime / float / integer / monetary / selection / text
```

Relational paths, protected fields, external/database id upserts and arbitrary related
record creation are not accepted in this slice.

Chunk claiming uses `FOR UPDATE SKIP LOCKED` only against the host-owned Assistant
session table. A chunk's business rows, cursor advance and durable receipt share one
PostgreSQL transaction boundary: a pre-commit crash rolls them back together; a
committed chunk is not blindly replayed.

For a validation-invalid chunk, the declared first-slice behavior is whole-chunk
rejection. Earlier committed chunks remain, the session becomes `partial` when
appropriate, and later unprocessed rows remain visible as `remaining_rows`.

Still deferred inside P11:

```text
XLS/XLSX/ODS durable sessions
relational import paths
external-id update/upsert
row-level salvage inside a rejected chunk
model-assisted row cleanup/enrichment and non-zero corrected_rows
interactive remap/resume after validation rejection
automatic final chat synthesis when background import completes
cross-session semantic duplicate matching
```

## 9. Validation truth

P10 is fully accepted on its immutable evidence.

P11 current status:

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

Use `research/P11_FOCUSED_VALIDATION_RUNBOOK.md`. Broad repository/addon/HOOT/Product
Behavior regressions remain periodic debt unless a focused failure or explicit gate
requires them.

## 10. Current follow-up scope

The immediate roadmap action is the focused P11 static/module/Odoo gate. Repair any
failure before consuming the slice in real P11 gates. After the six real import gates,
use their evidence to decide whether row-level correction/enrichment/remap is required
before P11 acceptance.

Later phases still include controlled source modification, multimodal/web evidence,
additional surfaces/automation and additional providers.
