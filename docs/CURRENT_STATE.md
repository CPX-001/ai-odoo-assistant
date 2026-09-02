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
P8.0 + P8.1/P8.2 checkpoint implemented; focused validation and P8 real gates pending
```

P7 acceptance is recorded in
`research/evidence/phase7/2026-09-02/P7-ACCEPTANCE-092ac57.md` and the final
accepted regression in
`research/evidence/regression/2026-09-02/FULL-REGRESSION-092ac57.md`.

No unexecuted P8 test or gate is a PASS.

## 1. Product/deployment baseline

- Target: Odoo 18 Community, self-hosted Linux.
- Supported product: `addons/odoo_ai_assistant`.
- Current addon manifest version: `18.0.13.19.0`.
- Current manifest dependencies remain `account`, `base`, `sale`, `web`.
- Runtime is embedded in Odoo; the browser talks only to authenticated Odoo routes.
- Odoo/PostgreSQL own conversation, turn, queue, effect/recovery and live-event state.
- Long turns are claimed by native `ir.cron` workers.
- Business operations run as the effective Odoo user with `su=False`.
- Codex App Server is the current concrete reasoning provider and remains an ephemeral/provider-owned runtime boundary.
- The retired FastAPI/Uvicorn Assistant sidecar is not part of the supported product.

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
```

`CapabilityDefinition` remains the atomic executable unit. There is no arbitrary
SQL, Python, shell, sudo or unrestricted `execute_method`/ORM-method escape hatch.

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
- per-turn immutable model/reasoning/autonomy/planning settings.

P8 does not replace this runtime or add another scheduler/database/agent loop.

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

## 6. P8.0 + P8.1/P8.2 Evidence foundation — implemented, not accepted

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

## 7. Runtime/installation Evidence and live projection

`assistant.runtime_inventory` is the first real EvidenceProvider. It derives a
bounded projection from the effective Odoo Environment containing:

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

The first live provider-neutral retrieval path is also implemented:

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

## 8. What P8 does not implement yet

The current checkpoint is not the complete Evidence product. Still pending are:

- durable reconnect restoration of the Evidence ledger through the existing Odoo working transcript;
- richer final-answer citation/navigation UX;
- runtime/schema/configuration/security/navigation providers beyond inventory;
- source/XML/module-document semantic indexing and validators;
- correlated log/traceback Evidence and automatic diagnosis;
- full host-owned observability spans/self-inspection capabilities;
- secret-value masked/copy/reveal UI;
- company Knowledge/RAG and uploaded Sources;
- repository/module acquisition and the Technical host privilege broker;
- domain-addon split and its clean install/update/uninstall proof.

These are later P8/P9/P10 work and must not be inferred from the foundation contracts.

## 9. Evidence/source scope

P8 uses an explicit current-source policy. Current addon/Odoo/install evidence is
preferred; retired sidecar/installer/migration/task/evidence history is excluded from
normal current-answer context by default without deleting history.

See:

- `EVIDENCE_ARCHITECTURE.md`
- `CONTEXT_SOURCE_POLICY.md`
- `runtime/context_source_policy.json`

## 10. Observability and secrets

ADR-023 and `OBSERVABILITY_ARCHITECTURE.md` define host-owned observability:
correlated turn/provider/capability/evidence/effect timing and outcomes, with detailed
content opt-in/redacted rather than logging prompts/args/results/secrets by default.

A user-pasted secret should not automatically block an otherwise safe turn. Derived
Evidence/progress/diagnostics should omit or redact it where possible and the user
should receive a warning without unnecessary re-emission. Assistant-presented
secrets require masked/copy/reveal UI before that product behavior can be claimed
complete.

## 11. Future technical/module operations

The product direction is **universal discovery + typed promotion**, not generic method
or shell execution. Installation/module operations will use bounded Evidence and
reviewed typed capabilities.

Arbitrary repositories may be candidates; they are not globally blocked merely for
being outside an allowlist. The future path is bounded web/repository preflight,
manifest/license/dependency/static inspection, compatibility/risk assessment and
policy-driven execution. Allowlists may be positive trust signals or customer policy,
not universal product authority.

ADR-024 remains **Proposed**. No privileged broker, repository acquisition, host
package installation or service operation is implemented by this P8 foundation.

## 12. Validation truth and next action

Current P8 validation debt is authoritative in `research/EXECUTION_STATE.md`.
The focused dependency-light tests, focused Odoo runtime-inventory test, immutable
context/planning regression and directly affected P7 extension/addon boundaries must
be executed in an Odoo/Codex-capable checkout and failures repaired before any P8
gate is claimed.

The GitHub connector can publish source changes but cannot substitute for those real
execution gates. P8 acceptance is not claimed. After focused validation, the next
integration work is durable ledger reconnect/citation UX and the source/XML/log real
gates rather than reimplementing the Evidence foundation again.
