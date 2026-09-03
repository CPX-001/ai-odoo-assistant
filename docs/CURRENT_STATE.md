# Current implementation state

This is the current-state entry point for the supported Odoo 18 product on `main`.
For the exact execution cursor, latest accepted evidence and unexecuted gates, use
[`research/EXECUTION_STATE.md`](research/EXECUTION_STATE.md).

## Accepted lineage

```text
P0-P4 accepted
P5.1-P5.8 accepted
P6 COMPLETE / ACCEPTED
P7 COMPLETE / ACCEPTED at 092ac57fe58a3a36765b115e78b2eca687f5dbbc
P8 COMPLETE / ACCEPTED at e370af8acb7df175c0a90c8e17520c8576b4c6ce
P9 COMPLETE / ACCEPTED at 77d470febf67ddee46562907718dc47e975922bb
```

P7 acceptance is recorded in
`research/evidence/phase7/2026-09-02/P7-ACCEPTANCE-092ac57.md` and the final
accepted regression in
`research/evidence/regression/2026-09-02/FULL-REGRESSION-092ac57.md`.

P8 acceptance evidence is recorded in
`research/evidence/phase8/2026-09-02/P8-ACCEPTANCE-e370af8.md`.

P9 implementation and validation runbook are recorded in
`research/P9_KNOWLEDGE_FIRST_SLICE.md` and
`research/P9_FOCUSED_VALIDATION_RUNBOOK.md`. Acceptance evidence is
`research/evidence/phase9/2026-09-03/P9-ACCEPTANCE-77d470f.md`.

## 1. Product/deployment baseline

- Target: Odoo 18 Community, self-hosted Linux.
- Supported product: `addons/odoo_ai_assistant`.
- Current addon manifest version: `18.0.13.23.0`.
- Current manifest dependencies remain `account`, `base`, `sale`, `web`.
- Runtime is embedded in Odoo; the browser talks only to authenticated Odoo routes.
- Odoo/PostgreSQL own conversation, turn, queue, effect/recovery, Evidence and Knowledge state.
- Long turns and bounded Knowledge ingestion are scheduled by native `ir.cron` workers.
- Business operations run as the effective Odoo user with `su=False`.
- Codex App Server is the current concrete reasoning provider and remains an ephemeral/provider-owned runtime boundary.
- The retired FastAPI/Uvicorn Assistant sidecar is not part of the supported product.
- Administrators use a standalone `AI Assistant` application menu for Knowledge,
  Diagnostics and Configuration. Operational surfaces are not hidden below Odoo's
  inline General Settings navigation.

The obsolete sidecar-testing GitHub Actions workflow, the `auth="none"` inventory
controller, its addon-local machine-authentication primitive and the residual
`services/instance_inventory.py` compatibility layer are removed from the supported
tree. Historical `service/` and `installer/` references remain only as
historical/regression evidence.

A future split into internal domain/link addons is allowed only if the customer still
experiences one installable Odoo AI Assistant product. Odoo's `auto_install` link-module
pattern is the preferred reference where it fits. No dependency is removed before
clean-install/update/uninstall validation proves the split safe.

## 2. Authority and effect model

The reasoning provider proposes; Odoo/host code remains authoritative for:

```text
user / companies / groups
ACL / record rules / field access
capability identity + schema + availability
budgets
policy / autonomy / approval
EffectPlan preparation
write barrier / execution
verification / recovery / receipts
public progress projection
Evidence access / freshness / trust
Knowledge source ownership / indexing lifecycle
```

`CapabilityDefinition` remains the atomic executable unit. There is no arbitrary
SQL, Python, shell, sudo or unrestricted `execute_method`/ORM-method escape hatch.
The P9 FTS SQL is fixed, parameterized host code and is not exposed as a capability.

Effects follow the existing host-owned lifecycle:

```text
discover/resolve
 -> inspect schema/preconditions
 -> prepare/preview
 -> policy
 -> approval when policy requires it
 -> execute
 -> verify
 -> receipt/recovery
```

Approval is policy/autonomy-driven, not a mandatory confirmation for every write.
Full-control may remove redundant confirmations for operations the effective user is
already allowed to perform and that policy marks auto-executable. It never enlarges
Odoo authority, and ambiguous effects are never blindly retried.

## 3. Durable agent runtime

The accepted P5/P6 runtime remains current:

- durable conversations and `odoo.ai.turn` records;
- queue/lease/cancel/stale recovery;
- one active causal turn per conversation with cross-conversation concurrency;
- provider-neutral `NextDecision` loop;
- bounded TaskPlan for public orchestration and separate typed EffectPlan for effects;
- bounded query/batch/workflow capabilities;
- EffectJournal and recovery-unit semantics;
- Stop/corrections/interventions;
- public activity, answer-delta streaming and final reconciliation;
- per-turn immutable model/reasoning/autonomy/planning settings;
- exact bounded resource references from verified prior effects for natural cross-turn follow-ups;
- structured capability/prepare/preflight/execution error feedback into the bounded model loop;
- safe host-authored final fallbacks when correction budgets end, without executing incomplete plans;
- protected-contact exclusions and explicit approval previews across both delete capability routes.

P8/P9 do not replace this runtime or add another scheduler/database/agent loop.

## 4. P7 extension framework — accepted and P8-hardened

P7 is accepted and live. The framework includes:

```text
CapabilityProvider
SkillDefinition / SkillCatalog
ContextProvider / ContextProviderCatalog
AssistantExtensionCatalog
ProviderProfile
EffectiveAssistantManifest
Odoo-registry provider discovery/composition
optional-provider failure isolation
progressive-disclosure state model
```

P8 hardens this same framework rather than creating another tool/plugin system:

- `CAPABILITY_PROVIDER_API_VERSION = "1"` is explicit;
- core provider/resource namespaces are reserved;
- API mismatch, loader, collision, dependency/version and cycle failures are isolated to attributable optional providers;
- required providers fail closed;
- capability/group guards fail closed on exceptions;
- capability/context/Skill/provider JSON contracts are deeply immutable while preserving normal `dict`/`list` type checks;
- trusted installed extensions may contribute capabilities, Skills, ContextProviders and EvidenceProviders through the same accepted provider boundary.

P9 reuses this extension/Evidence framework. `assistant.company_knowledge` is another
EvidenceProvider and `assistant.knowledge.ingest_attachment` is another
CapabilityDefinition; no Knowledge-specific registry is introduced.

## 5. Public product profiles

Product-facing behavior exposes exactly two values:

```text
user
technical
```

Historical/internal compatibility values such as `business` or `developer` still
exist in the internal access-profile seam, but public manifest projection normalizes
them to `user` / `technical`. The Technical/host privilege boundary proposed for P10
is an execution boundary, not a third human product profile.

Profile mapping does not grant permission. Odoo ACLs/policy remain authoritative.

## 6. P8 Evidence foundation and diagnosis — accepted

The current tree implements:

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

Key properties:

- finite/canonical JSON and deep immutable metadata;
- `FrozenDict`/`FrozenList` compatibility for callers using `isinstance(dict/list)`;
- bounded refs/excerpts/bytes;
- logical locators instead of model-authored arbitrary paths;
- provenance, fingerprint/freshness and access binding;
- secret redaction in Evidence structures;
- fine-grained optional provider failure isolation;
- fetch-time access recheck;
- explicit conflict groups;
- Evidence is untrusted data and cannot grant capabilities, policy or approval.

The bounded ledger retains at most 64 refs, 16 excerpts, 8 KiB per excerpt and 64 KiB
total. Its snapshot is serializable/versioned. The current live wrapper keeps it
turn-scoped; durable reconnect restoration is not claimed yet.

`EffectiveAssistantManifest.evidence_provider_ids` is reused as the manifest seam;
there is no second Evidence manifest/registry.

## 7. Runtime/source/log Evidence and live projection

`assistant.runtime_inventory` derives a bounded projection from the effective Odoo
Environment containing:

```text
Odoo release/edition
hashed database identity
installed modules + safe version metadata
registry fingerprint
user-vs-technical visibility
```

It intentionally excludes absolute addon roots, raw database names, credentials,
host commands and mutable business snapshots. Mutable business facts continue to
come from live ORM. A fingerprint change is surfaced as stale Evidence rather than
silently treating an old reference as current.

`assistant.source_evidence` performs bounded source/XML search only inside resolved
installed-addon roots, using logical locators, line citations and fingerprints.
`assistant.log_evidence` performs bounded correlated scans of the configured Odoo
logfile with secret redaction and opaque byte locators. Both are Technical resources
and neither creates execution authority.

The live provider-neutral retrieval path is:

```text
AssistantExtensionDecisionEngine
 -> effective Evidence provider IDs
 -> question-sensitive EvidenceRoutingPolicy
 -> bounded search/fetch through AssistantEvidenceDecisionEngine
 -> bounded turn EvidenceLedger
 -> host_assistant_evidence structural metadata
 -> assistant_evidence untrusted working data
 -> current reasoning provider
```

Generic/social turns can select no Evidence provider. Relevant installation/how-to/
diagnosis questions can retrieve Evidence. Codex only adapts the existing trust
partition; it does not gain an Evidence-specific authority path. Retrieved text,
including prompt-injection text, remains untrusted data.

## 8. P9 company Knowledge first slice — accepted

P9 now adds Odoo-native company Knowledge on top of that accepted Evidence path:

```text
odoo.ai.knowledge.source
  uploaded -> processing -> indexed -> active
                      \-> error

odoo.ai.knowledge.chunk
  derived host-owned lexical index rows

odoo.ai.knowledge.attachment
  temporary owner/company-bound chat upload

assistant.company_knowledge
  DOCUMENT EvidenceProvider

assistant.knowledge.ingest_attachment
  explicit-user-request plan capability
```

Initial ingestion is deterministic and bounded to TXT/Markdown/RST/CSV/JSON/XML,
8 MiB per source, 6,000 characters per chunk and 2,048 chunks per source. PostgreSQL
`simple` FTS plus a GIN expression index and bounded substring fallback form the
lexical baseline. Embeddings/vector storage are intentionally absent until evals
prove they materially improve retrieval.

Company Knowledge uses effective Odoo ACL/record rules before FTS. `company` sources
are visible only in active allowed companies; `private` sources are owner-only.
Source owner/company/lifecycle metadata is host-owned, and ordinary users cannot
mutate derived chunks. Search/fetch returns `USER_CONTENT` Evidence with source,
version, chunk and fingerprint citations. Reindex/version change makes old refs stale;
disabled sources are revoked.

The Assistant composer can upload a bounded temporary file. Upload alone does not
persist the file as Knowledge. When the user explicitly asks to add it, an opaque
marker is validated/stripped server-side, a host-only descriptor is bound to the
durable turn, and `assistant.knowledge.ingest_attachment` may create the persistent
source through the same plan/capability runtime. Raw base64 never enters the model
prompt.

This implementation is accepted at `77d470febf67ddee46562907718dc47e975922bb`.
Focused validation and all seven real Odoo/Codex gates passed with effective-user
`su=False`.

## 9. Explicit follow-up scope after this P9 slice

Still pending are:

- durable reconnect restoration of the Evidence ledger through the existing Odoo working transcript;
- richer citation navigation beyond persisted final-result metadata;
- runtime/schema/configuration/security/navigation providers beyond inventory;
- full host-owned observability spans/self-inspection capabilities;
- secret-value masked/copy/reveal UI;
- PDF/OCR/XLSX-specific Knowledge parsing;
- semantic/vector retrieval only if evals justify it;
- repository/module acquisition and the Technical host privilege broker;
- domain-addon split and its clean install/update/uninstall proof.

These are later P10+ follow-ups and must not be inferred from P9 acceptance.

## 10. Evidence/source scope

P8/P9 use an explicit current-source policy. Current addon/Odoo/install evidence is
preferred; retired sidecar/installer/migration/task/evidence history is excluded from
normal current-answer context by default without deleting history.

See:

- `EVIDENCE_ARCHITECTURE.md`
- `KNOWLEDGE_INDEX.md`
- `CONTEXT_SOURCE_POLICY.md`
- `runtime/context_source_policy.json`

## 11. Observability and secrets

ADR-023 and `OBSERVABILITY_ARCHITECTURE.md` define host-owned observability:
correlated turn/provider/capability/evidence/effect timing and outcomes, with detailed
content opt-in/redacted rather than logging prompts/args/results/secrets by default.

A user-pasted secret should not automatically block an otherwise safe turn. Derived
Evidence/progress/diagnostics should omit or redact it where possible and the user
should receive a warning without unnecessary re-emission. Assistant-presented
secrets require masked/copy/reveal UI before that product behavior can be claimed
complete.

Knowledge/source content is also untrusted data. A document cannot redefine
system/tool policy or grant execution authority.

## 12. Future technical/module operations

The product direction is **universal discovery + typed promotion**, not generic method
or shell execution. Installation/module operations will use bounded Evidence and
reviewed typed capabilities.

Arbitrary repositories may be candidates; they are not globally blocked merely for
being outside an allowlist. The future path is bounded web/repository preflight,
manifest/license/dependency/static inspection, compatibility/risk assessment and
policy-driven execution. Allowlists may be positive trust signals or customer policy,
not universal product authority.

ADR-024 remains **Proposed**. No privileged broker, repository acquisition, host
package installation or service operation is implemented by P8/P9.

## 13. Validation truth and next action

P8 passed `61` focused dependency-light tests, `20` focused Odoo tests and all six
real Odoo/Codex Evidence gates with effective-user `su=False`.

P9 focused validation passed: 49 dependency-light tests, 25 focused Odoo tests,
focused HOOT and the required composer browser smoke. The acceptance resume added a
bounded natural-query FTS repair, then passed its 10 dependency-light boundary/routing
tests, 4 focused Odoo test methods and all seven real Odoo/Codex Knowledge gates with
effective-user `su=False`. P9 is accepted and P10 is eligible. P10 must begin with the
mandatory privilege-boundary ADR before implementing host-operation capabilities.

The broad repository/addon/HOOT/Product Behavior FULL regressions remain periodic debt
unless a concrete later failure requires widening the validation scope.
