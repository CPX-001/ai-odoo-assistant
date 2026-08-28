# Agentic product evolution playbook

Research/product decision date: 2026-08-28  
Initial inspected implementation baseline: `24b9460ad09998ec50d853e0a715b543e5991bbb`  
Target: Odoo 18 Community, one global Assistant, provider-neutral runtime, Codex primary  
Status: ordered execution guidance; not current-state authority

This playbook begins **after Foundation Phases 0-4**. It turns the stabilized host/runtime into the broad general Odoo agent defined in `../PRODUCT_VISION.md`.

The product principle is:

> Restrict authority, not intelligence.

No phase may weaken effective-user Odoo authority, capability validation, policy, approval, write-barrier, verification or recovery merely to make the model feel more capable.

---

# 1. Execution and validation rules

## 1.1 Formal prerequisite

Do not select Phase 5 until all mandatory P2, P3 and P4 real-environment gates are PASS on the exact accepted implementation lineage.

At the playbook creation point, Phase 3/4 implementation exists on `main` but is not formally accepted. The required order is:

```text
P2 five real gates PASS
  -> P3 four real gates PASS
      -> P4 four real gates PASS
          -> Phase 5 may start
```

A failed gate creates a repair slice in the phase that owns the failure. Do not compensate with downstream code.

## 1.2 Every phase has four validation layers

A phase may become `COMPLETE` only when all applicable layers pass:

```text
A. static/contract validation
B. deterministic executable tests
C. agentic/eval battery
D. named real Odoo/product-path validation
```

Tests not runnable in the current environment remain debt. They are never converted to PASS.

## 1.3 Blocking rule

Unless a phase explicitly marks a gate `SOFT`, its completion gates are `HARD` for the next phase.

Only bounded preparation that does not consume the unvalidated contract may occur under `CONTINUOUS_EXECUTION_PROTOCOL.md`. After the already-landed P3/P4 look-ahead, the default is **no additional contract-layer look-ahead until P2-P4 validation debt is processed**.

## 1.4 Cross-phase invariants

Every slice preserves:

- Odoo as operational/persistence authority;
- effective-user Odoo business access with `su=False`;
- `CapabilityDefinition` as the atomic executable contract;
- no model-generated arbitrary method/SQL/Python/shell authority;
- explicit technical privilege boundary for host operations;
- preview/policy/approval before protected effects;
- durable write barrier before first effect;
- verification and recovery/no-blind-retry after ambiguous effects;
- retrieved/source/log text as untrusted data, never policy;
- private reasoning not exposed as public activity;
- one product Assistant identity; Skills are composition, not separate authority-owning agents;
- no parallel chat/MCP/automation tool registries;
- no GitHub Actions for this roadmap while repository instructions prohibit them.

## 1.5 Continuous agentic eval suite

Phase 5 establishes a small permanent conversational/agentic eval set. Every later phase extends it. Changes to prompts, provider adapters, tool descriptions, disclosure, context assembly, retrieval routing, budgets or provider settings must rerun the relevant subset.

Grade outcomes and invariants rather than exact hidden reasoning/tool order when several valid paths exist.

Track at minimum:

```text
task success
correct capability/skill selection
schema-valid call rate
unsupported-call rate
grounding/evidence quality
clarification quality
conversation continuity
unauthorized write rate = 0
recovery correctness
provider/tool failures correctly classified
latency / time to first useful activity / answer
read/retrieval call count
write/effect count
token/cost where available
```

---

# 2. Phase 5 — Natural chat, post-effect synthesis and conversation continuity

Goal: make the stabilized runtime feel like a capable conversational agent rather than a workflow bot.

This phase does **not** add broad new permissions, RAG or host tools.

## P5.1 — Finalize activity + answer + failure UX

Build on the real P3/P4 channels:

- user message appears immediately;
- public activity is visually separate from Assistant prose;
- provisional answer text streams independently;
- authoritative final answer reconciles without duplication;
- failure/approval/recovery states have dedicated presentation;
- cancel remains available for running safe work;
- no fake `Pensando…` assistant message when honest activity exists.

### Deterministic gate

HOOT/JS tests cover state transitions, reconnect/cursor ordering, cancellation, activity expansion, answer reconciliation, failures and approval/recovery rendering.

## P5.2 — Resume reasoning after verified effects

Current behavior ends an executed plan with host-generated completion text. Replace that product behavior with a host-owned continuation step:

```text
verified effect receipt/result
  -> append typed authoritative working item
  -> ask ReasoningProvider for next decision
  -> provider may inspect/retrieve more or produce final answer
```

The provider does not regain effect authority. A verified receipt is model input, not authorization for another write.

The natural final response should summarize what changed, what verification found and any important caveat.

### Deterministic gate

- verified receipt is appended once;
- provider continuation cannot duplicate the completed effect;
- restart after effect receipt reconstructs safely;
- cancellation/failure semantics remain correct;
- final synthesis may be long enough for the request and is not replaced by a fixed completion phrase.

## P5.3 — ConversationContextManager

Replace fixed `last 8 messages / bounded concatenated text` as the only conversational context strategy.

Introduce bounded host-owned conversation context with at least:

```text
recent raw messages
rolling structured summary
active entities/references
relevant previous evidence refs
relevant verified effect receipts
conversation/session settings
```

All original messages remain Odoo-owned history. Summary/reference state is derived context, not authority.

Continuations such as these must work reliably:

```text
"Analiza las ventas de Ana este mes."
"Compáralas con el anterior."
"Ahora sin Francia."
"Haz un resumen detallado."
```

## P5.4 — Explicit conversation/session preferences

Allow the user to change supported session behavior conversationally through host capabilities/settings, for example autonomy or response mode for the current conversation.

A phrase such as `no vuelvas a pedirme permiso para cambios normales en este chat` must become a bounded conversation policy override only if allowed by system/admin ceilings. It must not silently override protected-action rules.

## P5.5 — Conversational product eval baseline

Create at least these eval families:

```text
hello / small talk
what_can_you_do
unsupported_or_permission_limited_capability
follow-up references
pronoun/entity continuity
ambiguous record / useful clarification
read -> follow-up
read -> action
approval
post-effect synthesis
failure explanation
long detailed answer
session preference change
```

Start with at least 25 representative conversations and preserve them as a growing suite.

## Phase 5 real gates — HARD

```text
P5-REAL-CHAT-BASIC
P5-REAL-POST-EFFECT
P5-REAL-CONTINUITY
P5-REAL-SESSION-POLICY
P5-REAL-ERROR-UX
P5-REAL-APPROVAL-UX
P5-REAL-RECOVERY-UX
```

Pass requires a real Odoo 18 browser/product path with configured provider. Phase 6 is blocked until all mandatory P5 gates pass.

---

# 3. Phase 6 — Agent planning, multi-step effects, budgets and effect journal

Goal: support Codex-level task depth without weakening effect safety.

## P6.1 — Separate TaskPlan from EffectPlan

Introduce explicit terminology/contracts:

```text
TaskPlan
  high-level mutable plan for investigation/resolution
  no execution authority

EffectPlan
  host-validated proposed state changes
  carries exact capabilities/arguments/preconditions/effects
```

TaskPlan may be used by a deliberate Plan mode and may be shown to the user as high-level progress. It never contains/exposes private chain-of-thought.

## P6.2 — Adaptive vs deliberate strategy

Support:

```text
adaptive/default
  start with small context; discover/retrieve iteratively

deliberate/plan
  form a high-level task plan
  discover required skills/tools/context/evidence
  execute investigation
  revise plan if needed
```

An `auto` product mode may select deliberate strategy for complex work. Provider-specific hidden reasoning remains private.

## P6.3 — Multi-step EffectPlan

Evolve the one-step current action representation into a bounded plan of multiple `CapabilityDefinition` steps.

Every step retains:

```text
capability + version
validated arguments
preview
precondition fingerprint
risk/effect
approval decision
verification
receipt
```

Define ordering/dependency semantics. Do not permit a generic script body to replace typed steps.

## P6.4 — Atomic vs segmented effects

Explicitly distinguish:

- Odoo-local effects that can share one transaction/barrier/recovery unit;
- segmented effects requiring multiple durable checkpoints;
- external/non-transactional effects.

A mixed plan must not imply atomic rollback when the underlying systems cannot provide it.

## P6.5 — Separate budgets

Replace one broad notion of tool-call budget with at least:

```text
SafetyBudget
ExplorationBudget
CostBudget
LatencyBudget
ResponseBudget
```

Read/retrieval exploration should be configurable and substantially more generous than destructive effects, while retaining hard loop ceilings.

## P6.6 — Recent EffectJournal

Add a bounded Odoo-owned recent operation journal for Assistant effects.

For a configurable short TTL, retain only enough sanitized before/after/receipt data to support:

- explain what the Assistant changed;
- identify affected records;
- prepare a safe inverse operation where genuinely reversible;
- reconstruct recently deleted data where feasible.

Every operation is classified:

```text
reversible
reconstructable
irreversible
external_or_unknown
```

This is not a general database backup and must have retention/cleanup bounds.

## Phase 6 deterministic/eval gate

Required cases include:

- 2-5 step Odoo-local plan;
- step dependency ordering;
- precondition change between preparation/execution;
- approval at plan/step boundaries;
- failure before first effect;
- failure between segmented effects;
- worker loss after barrier;
- provider restart without effect replay;
- TaskPlan replan after new evidence;
- exploration loop hits configured ceiling cleanly;
- effect journal retention/cleanup;
- reconstructable delete does not claim identical rollback when impossible.

## Phase 6 real gates — HARD

```text
P6-REAL-MULTISTEP
P6-REAL-REPLAN
P6-REAL-EFFECT-ATOMICITY
P6-REAL-SEGMENTED-RECOVERY
P6-REAL-LOOP-BOUNDS
P6-REAL-EFFECT-JOURNAL
```

Phase 7 is blocked until the plan/effect model is stable.

---

# 4. Phase 7 — Effective Assistant environment, mini-framework and self-awareness

Goal: make the Assistant extensible and aware of its real effective capabilities without exposing every detailed schema on every turn.

## P7.1 — CapabilityProvider extension API

Allow trusted installed addons to contribute capabilities without modifying the core provider package.

Requirements:

- deterministic provider identity/version;
- duplicate/conflict rejection;
- failure isolation so one broken optional provider does not corrupt core discovery;
- explicit trusted-code loading only, no arbitrary host package scan;
- `CapabilityDefinition` remains the executable authority unit.

## P7.2 — Skill/Bundle metadata

A Skill groups semantic behavior without owning execution authority.

Target metadata may include:

```text
stable name/title/description
user-facing abilities/examples
instructions
capability selectors
context-provider selectors
evidence-provider selectors
activation conditions/configuration
tags/eval ownership
```

There remains one user-facing Assistant.

## P7.3 — ContextProvider contract

Introduce a provider-neutral way for trusted extensions to supply bounded JIT context. Context data is not authority and cannot register tools/policy from retrieved text.

Examples:

- current module inventory;
- active view/action/menu details;
- domain-specific business context;
- provider-specific feature context.

## P7.4 — ProviderProfile feature negotiation

Every reasoning provider exposes sanitized feature support such as:

```text
structured_output: native|emulated|unavailable
tool_calling: native|emulated|unavailable
answer_streaming: native|emulated|unavailable
vision: native|emulated|unavailable
file_input: native|emulated|unavailable
web: native|emulated|unavailable
large_context: native|emulated|unavailable
```

Do not implement a second provider yet unless needed for a conformance stub. This contract prevents future features from becoming Codex-only assumptions.

## P7.5 — EffectiveAssistantManifest

Build a host-derived projection of what the Assistant can actually use in this turn/context:

```text
provider/features
technical profile
effective skills
available/revealed capabilities
context providers
evidence/knowledge sources
configuration state
unavailable known feature + reason when safe
```

This manifest powers natural self-description and capability discovery.

## P7.6 — Technical access profile skeleton

Separate technical reach from confirmation autonomy.

At minimum establish:

```text
Business/User
Developer/Operator
```

No privileged host operation is added merely by defining the profile. Later phases bind technical capabilities to it.

## P7.7 — Progressive disclosure

When catalog scale warrants it, introduce high-level Skill/namespace awareness and deferred detailed capability schemas.

Keep common Odoo discovery/query primitives eager where evals show that is better. A hidden/disabled capability never becomes callable merely because the model names it.

## Phase 7 deterministic/eval gate

Use a trusted test addon that contributes:

- one Skill;
- one read capability;
- one plan capability;
- one ContextProvider;
- configuration metadata.

Required evals:

- `what can you do?` mentions installed/effective feature naturally;
- disabled capability is explained but not callable;
- missing configuration is distinguishable from missing permission/provider support;
- 100+ synthetic capability catalog does not materially regress selection when progressive disclosure is enabled;
- user explicitly asks for hidden tool -> host still denies it.

## Phase 7 real gates — HARD

```text
P7-REAL-PROVIDER-DISCOVERY
P7-REAL-SELF-AWARENESS
P7-REAL-DISABLEMENT
P7-REAL-CONTEXT-PROVIDER
P7-REAL-DISCLOSURE
P7-REAL-AUTHORITY
```

Phase 8 is blocked until extensions/self-awareness work through the real product path.

---

# 5. Phase 8 — Evidence foundation and installation intelligence

Goal: give the Assistant rich installation-specific evidence before building generic document RAG.

## P8.1 — Evidence contract

Define a bounded provider-neutral `Evidence` contract with at least:

```text
evidence_id
kind
source/provider
logical locator/title
bounded excerpt/data
provenance
fingerprint/version
captured_at/freshness
trust classification
access scope
citation metadata
status
```

Evidence is model input, never policy/authority.

## P8.2 — EvidenceLedger

Persist or retain bounded evidence references sufficient for:

- provider continuation;
- citations/provenance;
- conversation references;
- audit/debug of what supported an answer;
- stale/fingerprint checks.

Do not duplicate unrestricted raw source/log/business data indefinitely.

## P8.3 — EvidenceProvider contract and routing

Allow providers to search/fetch evidence through host contracts. Add an `EvidencePolicy`/routing layer so source priority varies by question rather than one universal ranking.

Host may require installation evidence before accepting claims that must be verified against the current instance.

## P8.4 — Runtime/schema/config evidence

Normalize current runtime/module/schema/configuration facts into Evidence where useful while preserving live Odoo authority.

## P8.5 — Source/XML intelligence

Reintroduce the useful sidecar-era concepts in embedded form, not the old service:

```text
source.find_symbol
source.find_model_extensions
source.find_view_or_xml_relations
source.read_excerpt
```

Use logical refs/fingerprints and bounded excerpts. Do not expose unrestricted filesystem paths merely because source is readable.

## P8.6 — Log/traceback evidence

Introduce structured Odoo log search + bounded context reads. Search should support time/component/severity/correlation hints so `analiza el error al confirmar este pedido` can choose the relevant traceback rather than literal last log entry.

PostgreSQL/host diagnostics may begin read-only here if they require no new privilege boundary; privileged operations wait for Phase 10.

## Phase 8 deterministic/eval gate

Required scenarios:

- installation-specific model/view/source question;
- standard Odoo question where official/general knowledge is initially plausible but runtime verification changes/strengthens answer;
- custom addon override diagnosis;
- recent traceback correlated to current record/action;
- stale source fingerprint rejected/re-fetched;
- retrieved prompt injection cannot alter policy/tools;
- conflicting evidence reported rather than silently merged;
- provenance survives multi-step synthesis.

## Phase 8 real gates — HARD

```text
P8-REAL-SOURCE-DIAGNOSIS
P8-REAL-LOG-DIAGNOSIS
P8-REAL-PROVENANCE
P8-REAL-FRESHNESS
P8-REAL-EVIDENCE-POLICY
P8-REAL-INJECTION-BOUNDARY
```

Phase 9 is blocked until the Evidence contract is proven.

---

# 6. Phase 9 — Company Knowledge and RAG

Goal: add configurable company knowledge without turning every message into generic vector search.

## P9.1 — KnowledgeSource model and UI

Create Odoo-native source records with lifecycle:

```text
uploaded/discovered -> processing -> indexed -> active
                                \-> error
```

Track version/fingerprint, type, status, access scope, indexing metadata and last processing result.

Initial source types should prioritize uploaded documents/files. External Drive/SharePoint-style connectors remain deferred.

## P9.2 — Ingestion pipeline

Implement bounded extraction and coherent segmentation.

Large documents must be processed by bounded Odoo-owned jobs/chunks. The model should not receive an entire large file in one prompt merely to create the index.

## P9.3 — Lexical/FTS retrieval first

Reintroduce a current embedded version of:

```text
knowledge.search
knowledge.read_excerpt
```

with PostgreSQL/Odoo-native lexical search where sufficient, logical refs, current fingerprint revalidation and citations.

## P9.4 — Chat-driven ingestion

An authorized user may attach a file and ask `añade esto al RAG/conocimiento`. The Assistant should create/configure the source, launch processing and report status through normal capability/activity semantics.

## P9.5 — Semantic/hybrid retrieval only when justified

Build a representative knowledge eval set before selecting vector storage/embedding/reranking.

Add semantic/vector retrieval only if it materially improves recall/task answer quality over lexical/structured search for target corpora. Prefer PostgreSQL-native storage if it meets requirements; do not require a separate vector service without evidence.

If semantic retrieval is added, keep source citation/fingerprint/ACL semantics identical.

## Phase 9 deterministic/eval gate

Required cases:

- exact term lookup;
- paraphrase lookup;
- long document section retrieval;
- multiple sources/citations;
- stale/reindexed source;
- disabled/deleted source;
- ACL-limited source;
- adversarial document text;
- conflicting company docs;
- chat upload -> process -> indexed -> answer;
- live business facts continue to come from live Odoo queries, not stale document/index snapshots.

## Phase 9 real gates — HARD

```text
P9-REAL-UPLOAD-INGEST
P9-REAL-CHAT-INGEST
P9-REAL-FTS
P9-REAL-CITATIONS
P9-REAL-ACL
P9-REAL-REINDEX
P9-REAL-LARGE-DOCUMENT
```

`P9-REAL-SEMANTIC-GAIN` is mandatory only if semantic/vector retrieval is implemented. It must demonstrate a measured quality gain rather than merely proving embeddings run.

---

# 7. Phase 10 — Developer/Operator and controlled host operations

Goal: allow technical users to diagnose and operate the real Odoo host without turning the model into unrestricted root authority.

This phase requires a new ADR before privileged host operations are implemented.

## P10.1 — Privilege-boundary ADR

Determine how operations unavailable to the normal Odoo OS user are performed.

Acceptable designs may include a narrow local broker/helper or tightly scoped privilege rules. The decision must define:

- allowed operation families;
- authentication/binding to Odoo user/profile/policy;
- command/config allowlists or schema contracts;
- filesystem path boundaries;
- timeouts/output caps;
- audit/events;
- restart/recovery semantics;
- installation/uninstallation behavior.

Do not grant broad passwordless root shell to the Odoo process.

## P10.2 — Module operations

Capabilities should cover at least:

```text
odoo.module.inspect
odoo.module.install
odoo.module.update
```

Module update/install must report actual result and relevant logs/errors back to reasoning.

## P10.3 — Odoo configuration

Provide bounded configuration inspection and patching of approved settings/paths, with preview/diff, policy and verification.

Editing `odoo.conf` is a host effect, not generic ORM CRUD.

## P10.4 — Process/service operations

Provide safe status/restart operations for approved Odoo-related services/processes when deployment supports them.

## P10.5 — PostgreSQL diagnostics

Add bounded health/activity/log/connection diagnostics. Administrative writes remain separate high-risk capabilities and are not implied by diagnostics.

## P10.6 — Console-style command fallback

Only after high-level operations are proven, evaluate a Developer-only bounded command capability for tasks not reasonably represented by dedicated capabilities.

It requires explicit path/command/environment restrictions, no secret dumping, output caps, timeout/cancellation and stronger approval/audit. It is not required to make ordinary business features work.

## Phase 10 deterministic/eval gate

Required cases:

- Business profile cannot see/call Developer-only operations;
- Full-access autonomy does not create Developer profile;
- module update success + failure logs;
- config preview/change/verify;
- service restart with health verification;
- privilege broker unavailable -> bounded useful failure;
- attempted path/command escape fails closed;
- provider text cannot alter broker policy.

## Phase 10 real gates — HARD

```text
P10-REAL-PROFILE-DENIAL
P10-REAL-MODULE-UPDATE
P10-REAL-CONFIG-PATCH
P10-REAL-SERVICE-OPERATION
P10-REAL-POSTGRES-DIAGNOSTIC
P10-REAL-PRIVILEGE-BOUNDARY
```

If generic command execution is enabled:

```text
P10-REAL-COMMAND-SANDBOX
P10-REAL-COMMAND-APPROVAL
```

Phase 11 is blocked until technical authority is proven safe.

---

# 8. Phase 11 — Advanced data operations and artifact workflows

Goal: make large imports/files first-class agent workflows rather than thousands of tiny CRUD calls.

## P11.1 — Artifact/attachment contract

Define bounded attachment/artifact references usable by chat/capabilities without putting binary/base64 payloads into prompts.

## P11.2 — DataImportSession

Implement durable staged import state:

```text
inspect file
 -> infer/choose model
 -> map columns
 -> validate types/relations
 -> identify duplicates/errors
 -> propose enrichment/corrections
 -> preview
 -> approval
 -> chunked ORM execution
 -> receipts/report
```

Codex may reason about ambiguous mappings/data cleanup, but host validation controls final values/effects.

## P11.3 — Resume and partial failure

Large imports must survive worker/provider interruption without blindly duplicating completed chunks. Row/chunk receipts make progress reconstructable.

## P11.4 — Recovery using EffectJournal

Imports/batch edits should integrate with the recent effect journal so the user can inspect exactly what the Assistant changed and prepare supported correction/reconstruction operations.

## Phase 11 real gates — HARD

```text
P11-REAL-CSV-IMPORT
P11-REAL-LARGE-IMPORT
P11-REAL-MAPPING-CORRECTION
P11-REAL-PARTIAL-INVALID
P11-REAL-RESUME-NO-DUPLICATE
P11-REAL-IMPORT-RECEIPT
```

---

# 9. Phase 12 — Controlled source-code modification workflow

Goal: support eventual Developer-only code changes without directly turning production addons into an unrestricted model workspace.

Source **read** already belongs in Evidence/Source Intelligence. This phase adds writes.

## P12.1 — Workspace/staging model

Code modifications occur in a bounded workspace/staging area with explicit source roots and snapshots/fingerprints.

## P12.2 — Patch/diff contract

The model proposes a bounded patch. Host validates paths, shows diff and records provenance.

## P12.3 — Test before deployment

Run applicable syntax/unit/Odoo update tests in a controlled environment before applying to the live source tree where feasible.

## P12.4 — Deploy/rollback boundary

Define how an approved patch is installed and how the prior source/config snapshot is restored if deployment fails. Do not imply transactionality across filesystem + Odoo DB where none exists.

## Phase 12 real gates — HARD

```text
P12-REAL-PATH-BOUNDARY
P12-REAL-DIFF-APPROVAL
P12-REAL-TEST-BEFORE-DEPLOY
P12-REAL-DEPLOY-VERIFY
P12-REAL-FAILED-DEPLOY-RECOVERY
```

This phase is Developer-only and may remain disabled by default in customer installations.

---

# 10. Phase 13 — Multimodal and web evidence

Goal: broaden perception while keeping all external content inside Evidence/Capability contracts.

## P13.1 — File/image routing

Route PDF/image/CSV/XLSX/etc. according to type and provider feature support.

Provider-native vision/file input may be used when supported. Otherwise use extraction/OCR capabilities and feed normalized Evidence.

## P13.2 — Web search/fetch

Add controlled evidence-oriented web search/fetch. No browser-control requirement.

Use it when:

- user explicitly needs external/current information; or
- local Odoo/runtime/Knowledge evidence is insufficient and policy permits external retrieval.

Web content remains untrusted and cited.

## Phase 13 real gates — HARD

```text
P13-REAL-PDF
P13-REAL-IMAGE-OCR-OR-VISION
P13-REAL-PROVIDER-FEATURE-FALLBACK
P13-REAL-WEB-SEARCH
P13-REAL-WEB-CITATION
P13-REAL-WEB-INJECTION-BOUNDARY
```

---

# 11. Phase 14 — Additional invocation surfaces and automation

Goal: reuse the same tested intelligence/authority outside the interactive chat.

Possible surfaces:

```text
MCP
scheduled/recurring Assistant tasks
AI fields
record/context launchers
automations/server actions
```

Rules:

- same `CapabilityDefinition`/registry/policy/executor;
- same Evidence/Context contracts;
- surface-specific effective catalog is allowed;
- no second tool authority list;
- unattended execution uses explicit automation policy/identity and stricter effect semantics;
- Odoo-native cron/queue is preferred for Odoo work when suitable;
- server recurring operations remain a distinct host capability class.

## Phase 14 real gates — HARD

At minimum for every implemented surface:

```text
P14-REAL-SURFACE-AUTHORITY
P14-REAL-SURFACE-CATALOG
P14-REAL-SURFACE-ACL
P14-REAL-SURFACE-EFFECT-POLICY
P14-REAL-SURFACE-RECOVERY
```

Automation additionally requires repeated-run/no-duplicate evidence.

---

# 12. Phase 15 — Additional reasoning providers

Goal: prove the product contract is provider-neutral without degrading all features to a minimum common denominator.

ProviderProfile from Phase 7 is mandatory first.

## P15.1 — API-backed provider

Implement one non-Codex provider through the same `ReasoningProvider`/decision contract where possible.

## P15.2 — Local provider

Add a local-model route only when a supported model can satisfy enough of the product contract to be useful. Unsupported features are explicitly `unavailable` or host-emulated.

## P15.3 — Feature parity matrix

The UI/Assistant manifest must show effective features accurately. Selecting a weaker provider must not silently pretend that vision, structured outputs, streaming or tool behavior are equivalent.

## Phase 15 real gates — HARD

For every promoted provider:

```text
P15-REAL-BASIC-CONVERSATION
P15-REAL-READ-TOOL
P15-REAL-ACTION-PROPOSAL
P15-REAL-STREAM-OR-DECLARED-FALLBACK
P15-REAL-CANCELLATION
P15-REAL-FAILURE-NORMALIZATION
P15-REAL-AUTHORITY-PARITY
P15-REAL-MANIFEST-ACCURACY
```

A provider may ship with explicitly unavailable optional features; it may not bypass host safety to imitate them.

---

# 13. Domain expansion rule

Sales/CRM/Accounting/Inventory and other domain features do not need to wait for one giant final `domain packs` phase.

Once Phase 7 extension contracts are stable, each domain Skill may be added as a vertical capability pack when it has a concrete product use case. Every pack must include:

- semantic capability definitions, not merely generic CRUD aliases;
- relevant context/evidence integration;
- permissions/policy;
- previews/verifications for effects;
- agentic eval tasks;
- named real product-path gates.

Prefer high-value semantic operations such as customer account summaries, quotation preparation, receivable diagnosis or stock-shortage analysis over hundreds of shallow one-method tools.

A domain pack cannot bypass the current phase's hard prerequisites. For example, source-backed accounting diagnosis waits for the Evidence layer; mass-import functionality waits for DataImportSession.

---

# 14. Performance discipline

Latency is cross-cutting rather than a one-off phase.

Keep Phase 0 timing checkpoints and extend them for context/retrieval/planning/import/host work. Before and after any material runtime optimization, compare at least:

```text
hello
simple read
multi-read analysis
one safe action
long streamed answer
current phase-specific representative task
```

A feature phase should not introduce a severe unexplained latency/cost regression. Use baseline-relative thresholds recorded in the slice rather than silently accepting slower behavior.

Do not optimize by weakening ACLs, removing verification, dumping huge context, disabling provenance or replacing safe operations with generic shell.

---

# 15. Roadmap summary

```text
P0  reproducible baseline                         COMPLETE
P1  provider boundary / host-owned decision loop  COMPLETE
P2  structured failure contract                   real gates pending
P3  truly live public activity                    implementation landed; acceptance pending
P4  real answer streaming                         implementation landed; acceptance pending

P5  natural chat + post-effect synthesis + continuity
P6  TaskPlan / multi-step EffectPlan / budgets / EffectJournal
P7  mini-framework + Assistant manifest + progressive discovery
P8  Evidence layer + source/runtime/log intelligence
P9  company Knowledge / RAG / ingestion
P10 Developer/Operator host operations
P11 advanced imports/artifact data workflows
P12 controlled source-code modification
P13 multimodal + web evidence
P14 additional surfaces / automation / MCP
P15 additional providers
```

The next implementation action is **not P5**. First close the real P2 -> P3 -> P4 validation chain recorded in `EXECUTION_STATE.md`.
