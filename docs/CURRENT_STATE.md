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
```

P10 is the latest accepted phase. Its evidence is
`research/evidence/phase10/2026-09-03/P10-ACCEPTANCE-bde508b.md`.

P10's accepted design and current implementation records are:

```text
adr/ADR-024-technical-host-privilege-broker.md
research/P10_HOST_OPERATIONS_FIRST_SLICE.md
research/P10_FOCUSED_VALIDATION_RUNBOOK.md
```

Code or a prepared test is not PASS evidence.

## 1. Product and deployment baseline

- Target: Odoo 18 Community, self-hosted Linux.
- Supported addon: `addons/odoo_ai_assistant`.
- Current addon manifest version: `18.0.13.26.0`.
- Current dependencies remain `account`, `base`, `sale`, `web`.
- The addon is exposed as an Odoo application with Knowledge, Diagnostics and
  Configuration menus; chat remains globally available from the systray.
- Runtime is embedded in Odoo; the browser talks only to authenticated Odoo routes.
- Odoo/PostgreSQL own conversations, turns, queue, effects, recovery, Evidence and
  Knowledge state.
- Long turns and bounded Knowledge ingestion use native `ir.cron` workers.
- Business operations run as the effective Odoo user with `su=False`.
- Codex App Server is the current concrete reasoning provider and remains an
  ephemeral/provider-owned subprocess.
- The retired FastAPI/Uvicorn Assistant sidecar is not part of the supported product.
- Knowledge and Diagnostics expose short customer-facing field help: editable inputs
  explain what to provide, while host-calculated and read-only values explain what they
  mean and what action, if any, the administrator should take.

The optional P10 host broker is a separate machine privilege adapter for finite host
operations. It is not the Assistant runtime, does not run the model and does not own
conversation/turn state.

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
```

`CapabilityDefinition` remains the atomic executable unit. There is no arbitrary SQL,
Python, shell, sudo or unrestricted ORM-method escape hatch.

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

Approval is policy/autonomy-driven. Full-control may remove a redundant confirmation
only for an operation already available to the effective user and allowed by trusted
policy. It never enlarges Odoo or broker authority. Ambiguous effects are not blindly
retried.

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
- safe host-authored fallback when correction budgets end;
- no replay of a completed or uncertain effect.

P7-P10 extend this runtime rather than adding another scheduler, database or agent loop.

## 4. Extension framework and product profiles

The live framework includes:

```text
CapabilityProvider
SkillDefinition / SkillCatalog
ContextProvider / ContextProviderCatalog
EvidenceProvider / EvidenceProviderCatalog
AssistantExtensionCatalog
ProviderProfile
EffectiveAssistantManifest
Odoo-registry provider discovery/composition
optional-provider failure isolation
progressive-disclosure state model
```

Trusted installed extensions may contribute definitions, Skills, ContextProviders and
EvidenceProviders. Every executable operation still resolves through the same
registry, executor, policy and effective user.

Product-facing profiles are exactly:

```text
user
technical
```

Historical `business`/`developer` values are internal compatibility names only.
Profile projection grants no permission, and autonomy is independent from technical
reach.

## 5. Evidence and installation intelligence — accepted P8

The shared non-executable Evidence layer provides:

```text
EvidenceKind / EvidenceTrust / EvidenceFreshness
EvidenceAccessScope / EvidenceLocator
EvidenceRef / EvidenceItem
EvidenceSearchRequest / EvidenceSearchResult
EvidenceProvider / EvidenceProviderStatus
EvidenceProviderCatalog
EvidenceRoutingPolicy
EvidenceLedger / EvidenceLedgerSnapshot
AssistantEvidenceDecisionEngine / EvidenceWorkingContext
```

Important properties:

- bounded/canonical immutable JSON;
- logical locators rather than model-authored arbitrary paths;
- access scope, provenance, fingerprint and freshness;
- secret redaction;
- optional-provider failure isolation;
- fetch-time access and freshness recheck;
- question-sensitive routing rather than a rigid intent router;
- retrieved text remains untrusted data and never grants authority.

Current live providers include runtime inventory, installed-addon source/XML and
configured-log Evidence. Installation-specific answers can use bounded current source
and log evidence; mutable business truth remains live ORM authority.

## 6. Company Knowledge — accepted P9

P9 adds:

```text
odoo.ai.knowledge.source
odoo.ai.knowledge.chunk
odoo.ai.knowledge.attachment
assistant.company_knowledge
assistant.knowledge.ingest_attachment
```

Source lifecycle is:

```text
uploaded -> processing -> indexed -> active
                      \-> error
```

The first pipeline deterministically handles bounded PDF, TXT, Markdown, RST, CSV, JSON and
XML. PostgreSQL `simple` FTS plus a GIN expression index and bounded substring fallback
form the lexical baseline. Company/private record rules apply before retrieval.
Fingerprint/version changes make old references stale. Embeddings/vector search remain
conditional on measured gain.

## 7. P10 Technical and host operations — accepted

ADR-024 is accepted. The first slice implements two Odoo-local Technical reads:

```text
odoo.module.inspect
postgres.health
```

It also implements an optional Linux AF_UNIX privilege broker and five broker-backed
capabilities:

```text
odoo.config.inspect
odoo.config.patch
host.service.status
host.service.restart
odoo.module.update
```

The broker boundary provides:

- exact logical targets from deployment-owned policy;
- bidirectional Linux `SO_PEERCRED` checks;
- bounded versioned request/receipt schemas;
- canonical args and EffectPlan binding fingerprints;
- fixed-argv service operations with `shell=False`;
- policy-bound module/database/runtime/UID/GID maintenance targets;
- external transient systemd module update plus fresh-registry verification;
- atomic config replacement, fsync and private backup;
- a durable SQLite execution ledger;
- terminal receipt replay for the exact request;
- replay mismatch denial;
- `uncertain` state for in-flight or post-dispatch transport/receipt loss;
- sanitized structured output only.

Technical capabilities require `base.group_system`. User/non-technical accounts cannot
discover or execute them even under full autonomy. Broker availability is an
additional guard and never a permission source.

Effectful broker operations retain the existing PLAN lifecycle with HOST risk/effect,
policy approval, preview, durable request binding, execute, verify and external
recovery classification.

### P10 explicit limits

Not implemented:

```text
odoo.module.install/uninstall
repository acquisition/promotion
host package installation
config rollback capability
secret-value reveal
generic command fallback
arbitrary SQL/Python/shell/sudo
```

Odoo module update is deliberately not called as an immediate ORM action from the
Assistant cron worker. It runs in a separate transient systemd unit under the
configured non-root identity and must pass a fresh-registry version check.

The reference systemd broker unit must be adapted and tested against exact deployment
paths. A disposable auxiliary service should be used for the first restart gate;
support for restarting the Odoo service itself is not inferred without lifecycle
reconciliation evidence.

## 8. Validation truth

Accepted P9 validation:

```text
49 focused dependency-light tests
25 focused Odoo tests
focused HOOT + browser/asset smoke
7/7 real Odoo/Codex Knowledge gates
```

P10 status:

```text
focused static/compile/lint                        PASS — bde508b
dependency-light broker/client tests               PASS — 18 tests
focused Odoo Technical/host tests                  PASS — 5 methods, 0 failures/errors
broker deployment/systemd smoke                    PASS
P10-REAL-PROFILE-DENIAL                            PASS
P10-REAL-CONFIG-PATCH                              PASS
P10-REAL-SERVICE-OPERATION                         PASS
P10-REAL-POSTGRES-DIAGNOSTIC                       PASS
P10-REAL-PRIVILEGE-BOUNDARY                        PASS
P10-REAL-MODULE-UPDATE                             PASS
P10 acceptance                                     COMPLETE / ACCEPTED
```

Use `research/P10_FOCUSED_VALIDATION_RUNBOOK.md`. Broad repository/addon/HOOT/Product
Behavior regressions remain periodic debt unless an explicit gate or a focused failure
requires them.

## 9. Current follow-up scope

The next roadmap work is Phase 11: inspect the current artifact/import seams and
design the largest coherent durable `DataImportSession` slice before implementation.

Other later work still includes richer citation navigation, durable Evidence-ledger
reconnect restoration, masked/reveal secret UX, PDF/OCR/XLSX parsing, optional
semantic retrieval, advanced imports, controlled source modification, additional
surfaces and additional providers.
