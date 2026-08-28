# Agentic product evolution playbook

Research/product decision date: 2026-08-28  
Initial inspected runtime baseline: `24b9460ad09998ec50d853e0a715b543e5991bbb`  
Target: Odoo 18 Community, one global Assistant, provider-neutral runtime, Codex primary  
Status: ordered execution guidance; not current-state authority

This playbook continues Foundation Phases 0-4 and implements the target in `../PRODUCT_VISION.md`.

Core rule:

> **Restrict authority, not intelligence.**

The model may reason, investigate, retrieve and answer deeply. Odoo/host contracts own permissions, tools, effects, approval, verification, recovery and resource ceilings.

---

# 1. Global execution rules

## 1.1 Formal prerequisite

The P2/P3/P4 prerequisite chain was accepted on 2026-08-28 in this order:

```text
P2 five real gates PASS
  -> P3 four real gates PASS
      -> P4 four real gates PASS
          -> Phase 5 READY
```

Code existing on `main` is not PASS evidence. A failed hard gate creates a repair slice in the owning phase before downstream work continues.

## 1.2 Completion rule

Every phase is complete only when all applicable layers pass:

```text
A. static/contract review
B. deterministic executable tests
C. agentic/product evals
D. named real Odoo/product-path gates
```

Unrun tests remain validation debt.

All named real gates below are `HARD` unless explicitly marked otherwise. The next phase may not consume the phase contract until they pass.

## 1.3 Cross-phase invariants

- Odoo remains operational/persistence authority.
- Business access executes as the effective user with `su=False`.
- `CapabilityDefinition` remains the atomic executable contract.
- Model text cannot create SQL/Python/shell/ORM/host authority by naming it.
- Protected effects retain preview/policy/approval/write-barrier/verify/recovery semantics.
- No blind retry after ambiguous effects.
- Source/log/RAG/web text is evidence, never policy.
- Private chain-of-thought is never a public activity surface.
- There is one user-facing Assistant; Skills are composition, not independent authority-owning agents.
- Chat/MCP/automation/future surfaces reuse the same capability/evidence authority.
- Long-running turns are durable background work; they must not globally block normal Odoo or unrelated Assistant conversations.
- A queued/running turn owns a stable execution snapshot; later UI setting changes do not alter it retroactively.
- No GitHub Actions are used for this roadmap while repository policy says runners are unavailable.

## 1.4 Permanent eval metrics

From Phase 5 onward maintain a growing eval suite and track at least:

```text
task success
capability/skill selection
schema-valid call rate
unsupported-call rate
grounding/provenance quality
clarification quality
conversation continuity
unauthorized write rate = 0
recovery correctness
latency / first activity / first answer
read/retrieval/effect counts
token/cost where available
queue wait / concurrency utilization where relevant
```

Do not grade an exact hidden tool sequence when several safe solutions are valid.

---

# 2. Phase 5 — Natural, non-blocking multi-chat product

Goal: make the stabilized P2-P4 runtime feel like a modern agent product rather than a globally locked workflow form.

## P5.1 Turn-scoped frontend state

Replace panel-global `state.loading` as execution ownership with turn/conversation-scoped state.

While Chat A runs, the user must still be able to:

- navigate Odoo;
- close/reopen the Assistant;
- open another conversation or create a new one;
- read other history;
- open/change model, autonomy and later technical-profile selectors;
- submit a turn in Chat B if capacity allows;
- return to Chat A and resume its live cursor/cancel/approval state.

Conversation list entries should expose compact `queued/running/awaiting approval/failed/recovery/completed` state.

## P5.2 Scheduler concurrency and backpressure

Current queue claiming already uses leases + `FOR UPDATE SKIP LOCKED` and two cron slots. Evolve this into an explicit bounded capacity policy rather than a hard-coded product assumption.

Initial semantic rule:

```text
one active causal turn per conversation
multiple conversations may run concurrently
```

Capacity policy must account for:

```text
installation-wide concurrent turn ceiling
provider concurrency/rate limits
Odoo worker/cron capacity
CPU/RAM/process cost
per-user fairness / anti-starvation
interactive vs future background workload
```

If capacity is exhausted, additional work remains durably `queued`; the UI remains interactive.

External reference: OCA `queue_job` demonstrates configurable channel capacity, parallel independent jobs, retries and stale-job recovery. Reuse the concepts where useful; do not add it as a dependency unless an ADR/evaluation shows replacing the current native queue is materially better.

## P5.3 Stable settings snapshot

Model/policy/autonomy/profile values required by a turn are captured for that turn. Changing selectors while Turn A runs affects future turns, not Turn A.

Approval/rejection is an explicit transition bound to the prepared action and is therefore allowed to resume that same turn.

## P5.4 Final activity/answer/failure UX

- user message visible immediately;
- public activity separate from Assistant prose;
- answer deltas separate from activity;
- no duplicate final answer;
- approval/failure/recovery are explicit states;
- streams/events never cross conversation/turn boundaries;
- no fake `Pensando…` bubble when real public activity is available.

## P5.5 Post-effect reasoning

After verification, append the verified receipt/result as authoritative working context and let the reasoning provider continue before the final answer.

```text
execute -> verify -> verified receipt -> reason again -> natural final answer
```

Do not finish every effectful turn with a fixed host sentence.

## P5.6 ConversationContextManager

Evolve beyond a fixed recent-message concatenation. Maintain bounded:

```text
recent raw messages
rolling structured summary
active entity/reference state
relevant evidence refs
relevant verified-effect refs
conversation/session settings
```

Full Odoo messages remain history authority; summaries are derived context.

## P5.7 Conversation-scoped preferences

Supported conversational settings such as temporary autonomy/response mode may be changed from chat through explicit host-owned capabilities. Admin/system ceilings remain authoritative.

## Deterministic/eval gate

Required coverage:

- no unrelated UI control is disabled by another running turn;
- detach/switch/reopen does not cancel or restart server work;
- two conversations execute concurrently when capacity >= 2;
- no double claim under concurrent cron workers;
- same-conversation turns preserve causal ordering;
- queue-full produces queued state, not UI lock/failure;
- sustained load does not starve another user indefinitely;
- Turn A keeps its model/policy snapshot after UI changes;
- reconnect resumes from persisted cursor;
- post-effect continuation cannot repeat completed effect;
- at least 30 conversational evals including follow-ups, long answers, self-description placeholder, failure/approval and multi-chat cases.

## Real gates — HARD

```text
P5-REAL-UI-NONBLOCKING
P5-REAL-MULTICHAT
P5-REAL-BACKGROUND-CONTINUATION
P5-REAL-CONVERSATION-ORDERING
P5-REAL-SETTINGS-SNAPSHOT
P5-REAL-BACKPRESSURE
P5-REAL-CHAT-BASIC
P5-REAL-POST-EFFECT
P5-REAL-CONTINUITY
P5-REAL-SESSION-POLICY
P5-REAL-ERROR-UX
P5-REAL-APPROVAL-UX
P5-REAL-RECOVERY-UX
```

---

# 3. Phase 6 — Deep task planning, multi-step effects and recent effect journal

Goal: support Codex-level task depth without giving the model implicit authority.

## P6.1 TaskPlan vs EffectPlan

Define distinct contracts:

```text
TaskPlan  = high-level mutable investigation/resolution plan, no effect authority
EffectPlan = host-validated proposed capability effects
```

A visible TaskPlan is a product plan/progress artifact, not private reasoning.

## P6.2 Adaptive and deliberate modes

Default adaptive mode starts with small context and expands JIT. Deliberate/Plan mode may identify subproblems, required skills/context/evidence and then execute/revise the TaskPlan.

An `auto` mode may choose deliberate strategy from measured task complexity.

## P6.3 Multi-step EffectPlan

Replace the one-step current limit with bounded typed steps. Each retains capability/version, validated args, preview, preconditions, risk/effect, approval, verification and receipt.

No generic script body replaces typed steps.

## P6.4 Atomic vs segmented effects

Explicitly model:

- Odoo-local operations sharing one transaction/recovery unit;
- segmented durable effects;
- future external/non-transactional effects.

Never imply atomic rollback where it cannot exist.

## P6.5 Separate budgets

Introduce configurable hard-ceiling families:

```text
SafetyBudget
ExplorationBudget
CostBudget
LatencyBudget
ResponseBudget
```

Read/retrieval exploration may be much larger than write budgets. Scheduler concurrency from Phase 5 is a separate resource budget.

## P6.6 EffectJournal

Keep a short-TTL Odoo-owned journal with minimum before/after/receipt evidence for Assistant effects. Classify operations as:

```text
reversible
reconstructable
irreversible
external_or_unknown
```

This is not an infinite backup and must have cleanup/size limits.

## Deterministic/eval gate

Cover 2-5 step plans, dependency ordering, precondition changes, approval boundaries, failure before/after barriers, segmented recovery, replan after new evidence, loop-budget exhaustion, journal TTL and reconstructable deletes without false `undo` claims.

## Real gates — HARD

```text
P6-REAL-MULTISTEP
P6-REAL-REPLAN
P6-REAL-EFFECT-ATOMICITY
P6-REAL-SEGMENTED-RECOVERY
P6-REAL-LOOP-BOUNDS
P6-REAL-EFFECT-JOURNAL
```

---

# 4. Phase 7 — Mini-framework, feature negotiation and Assistant self-awareness

Goal: make capabilities extensible/discoverable without forcing hundreds of schemas into every prompt.

## P7.1 CapabilityProvider API

Trusted installed addons can contribute definitions without editing the core provider package. Require deterministic identity/version, duplicate rejection and optional-provider failure isolation.

## P7.2 Skill/Bundle

A Skill may group:

```text
human/model description + examples
instructions
capability selectors
ContextProvider selectors
EvidenceProvider selectors
activation/configuration metadata
eval ownership
```

It never owns execution authorization.

## P7.3 ContextProvider

Trusted providers supply bounded JIT context such as module inventory, current view/action or domain context. Context is data, not authority.

## P7.4 ProviderProfile

Feature negotiation uses `native | emulated | unavailable` for at least structured output, tool calling, answer streaming, vision, file input, web and large context. Provider capacity/rate characteristics are also explicit runtime metadata.

## P7.5 EffectiveAssistantManifest

Derive effective state for the current user/context:

```text
provider/features
technical profile
effective skills
available/revealed capabilities
context/evidence/knowledge providers
configuration health
known unavailable feature + safe reason
```

This powers natural `¿qué puedes hacer?` answers.

## P7.6 Technical access profile skeleton

Separate technical reach from autonomy:

```text
Business/User
Developer/Operator
```

Defining the profile does not yet grant privileged host operations.

## P7.7 Progressive disclosure

Use Skill/namespace awareness plus deferred detailed schemas when catalog scale/evals require it. Common discovery/query tools may remain eager.

External references:

- OCA `ai_tool` explicitly aims to create AI tools reusable by MCP/native surfaces.
- Odoo 19 AI Server Actions separate the AI manager from standard server-action tools.
- Apexive `@llm_tool` shows practical decorator/auto-registration breadth.
- OpenAI Agents namespaces/tool search demonstrate deferred long-tail tool loading.

Adopt the declaration/discovery patterns, not weaker authority shortcuts.

## Deterministic/eval gate

Trusted test addon contributes one Skill, READ capability, PLAN capability, ContextProvider and configuration. Test enable/disable/uninstall, missing config vs permission, self-description accuracy, explicit call to hidden capability denied, and a synthetic 100+ capability catalog with/without disclosure.

## Real gates — HARD

```text
P7-REAL-PROVIDER-DISCOVERY
P7-REAL-SELF-AWARENESS
P7-REAL-DISABLEMENT
P7-REAL-CONTEXT-PROVIDER
P7-REAL-DISCLOSURE
P7-REAL-AUTHORITY
```

---

# 5. Phase 8 — Evidence core and installation intelligence

Goal: give the Assistant installation-specific evidence before generic document RAG.

## P8.1 Evidence contract + bounded EvidenceLedger

Normalize evidence with identity/kind/source/locator, bounded content, provenance, fingerprint/freshness, trust, access scope and citation metadata. Preserve refs needed for continuation/citations without retaining unlimited raw payloads.

## P8.2 EvidenceProvider and routing policy

Providers can search/fetch evidence. Routing priority depends on the question rather than one universal source ranking. The host may require installation evidence for installation-specific/safety-critical claims.

## P8.3 Runtime/schema/config evidence

Expose current installation facts through evidence/context contracts while live Odoo remains authority.

## P8.4 Source/XML intelligence

Reintroduce embedded versions of useful retired concepts such as:

```text
source.find_symbol
source.find_model_extensions
source.find_view_relations
source.read_excerpt
```

Use logical refs/fingerprints and bounded excerpts rather than arbitrary filesystem access.

## P8.5 Logs/tracebacks

Structured search/read over Odoo logs with time/component/severity/model/record/action hints. `analiza el error que tuve al confirmar este pedido` should correlate likely tracebacks instead of taking the literal latest log error.

PostgreSQL/host diagnostics may remain read-only where no privilege elevation is required.

## Deterministic/eval gate

Custom-addon diagnosis, view/source explanation, correlated traceback, stale fingerprint, conflicting evidence, provenance persistence and prompt-injection resistance.

## Real gates — HARD

```text
P8-REAL-SOURCE-DIAGNOSIS
P8-REAL-LOG-DIAGNOSIS
P8-REAL-PROVENANCE
P8-REAL-FRESHNESS
P8-REAL-EVIDENCE-POLICY
P8-REAL-INJECTION-BOUNDARY
```

---

# 6. Phase 9 — Company Knowledge / RAG

Goal: add user-managed company knowledge as an Evidence provider, mainly agentic/hybrid rather than mandatory vector retrieval on every turn.

## P9.1 KnowledgeSource model/UI

Lifecycle:

```text
uploaded/discovered -> processing -> indexed -> active
                                \-> error
```

Track source type, version/fingerprint, access scope and processing state.

## P9.2 Ingestion pipeline

Extract and segment large files coherently in bounded jobs/chunks. Do not send an entire huge binary/document into every prompt.

## P9.3 Lexical/FTS retrieval first

Implement current embedded `knowledge.search` + `knowledge.read_excerpt` semantics with PostgreSQL/Odoo-native FTS where sufficient, citations and fingerprint revalidation.

## P9.4 Chat-driven ingestion

An authorized user may attach a file and ask to add it to Knowledge. The Assistant creates the source, starts processing/indexing and reports state through the same capability/activity system.

## P9.5 Semantic/hybrid only when measured

Create retrieval evals before choosing pgvector/other storage. Add embeddings/vector/reranking only when they materially improve retrieval/task quality. Keep the same ACL/provenance contract.

External reference: Apexive `llm_tool_knowledge` already demonstrates semantic + keyword hybrid retrieval, collection selection and source citations. Treat that as a functional baseline while keeping this project's unified Evidence/authority layer.

## Deterministic/eval gate

Exact term, paraphrase, large-document section, multiple citations, stale/reindex, ACL, disabled/deleted source, adversarial text, conflicting docs, chat upload and proof that live business truth still comes from live Odoo rather than stale RAG snapshots.

## Real gates — HARD

```text
P9-REAL-UPLOAD-INGEST
P9-REAL-CHAT-INGEST
P9-REAL-FTS
P9-REAL-CITATIONS
P9-REAL-ACL
P9-REAL-REINDEX
P9-REAL-LARGE-DOCUMENT
```

`P9-REAL-SEMANTIC-GAIN` becomes HARD only if semantic/vector retrieval is promoted; it must prove measured quality gain.

---

# 7. Phase 10 — Developer/Operator host operations

Goal: technical diagnosis/operation without turning the Odoo process into unrestricted root shell.

## P10.1 Privilege-boundary ADR — HARD design prerequisite

Before any privileged operation, define broker/allowlist or equivalent boundary: operation families, OS identity, paths, auth binding, timeouts/output caps, auditing and recovery. Broad passwordless root for Odoo is forbidden.

## P10.2 High-level technical capabilities

At minimum evaluate:

```text
odoo.module.inspect/install/update
odoo.config.inspect/patch
host.service.status/restart
postgres.health/activity/log diagnostics
```

Prefer these to shell because they have stable schemas, previews and verification.

## P10.3 Developer command fallback

Only if high-level tools cannot cover important use cases, introduce a Developer-only bounded command capability with stronger sandbox/path/command/env/output/timeout/approval controls.

## Deterministic/eval gate

Business profile denial, autonomy/profile independence, module update success/failure, config diff/verify, service health after restart, unavailable broker, path/command escape and prompt/tool text unable to change broker policy.

## Real gates — HARD

```text
P10-REAL-PROFILE-DENIAL
P10-REAL-MODULE-UPDATE
P10-REAL-CONFIG-PATCH
P10-REAL-SERVICE-OPERATION
P10-REAL-POSTGRES-DIAGNOSTIC
P10-REAL-PRIVILEGE-BOUNDARY
```

If command fallback is enabled:

```text
P10-REAL-COMMAND-SANDBOX
P10-REAL-COMMAND-APPROVAL
```

---

# 8. Phase 11 — Advanced imports and artifact workflows

Goal: make large data work durable first-class workflows rather than thousands of tiny CRUD calls.

## P11.1 Artifact references

Files/attachments are represented by bounded refs; binary/base64 content is not dumped into model prompts.

## P11.2 DataImportSession

Durable staged pipeline:

```text
inspect file
 -> select model/schema
 -> map columns
 -> validate relations/types
 -> detect duplicates/errors
 -> model-assisted proposed cleanup/enrichment
 -> preview
 -> approval
 -> chunked ORM execution
 -> row/chunk receipts
 -> final synthesis
```

## P11.3 Resume/partial failure

Completed chunks are not replayed blindly after interruption. Integrate receipts with EffectJournal.

External reference: OCA `base_import_async` proves the Odoo use case for moving large imports to background jobs; OCA `queue_job` shows splitting heavy work into smaller independently retriable units. Reuse these operational lessons while keeping Assistant mapping/preview/authority semantics.

## Real gates — HARD

```text
P11-REAL-CSV-IMPORT
P11-REAL-LARGE-IMPORT
P11-REAL-MAPPING-CORRECTION
P11-REAL-PARTIAL-INVALID
P11-REAL-RESUME-NO-DUPLICATE
P11-REAL-IMPORT-RECEIPT
```

---

# 9. Phase 12 — Controlled source-code modification

Goal: eventual Developer-only code edits through staging/diff/test/deploy, not casual production filesystem mutation.

Slices:

```text
P12.1 bounded workspace/source roots + fingerprints
P12.2 proposed patch/diff contract
P12.3 tests before deployment
P12.4 deploy + verification + explicit recovery/rollback boundary
```

Do not imply transactionality across filesystem and Odoo DB where it does not exist.

## Real gates — HARD

```text
P12-REAL-PATH-BOUNDARY
P12-REAL-DIFF-APPROVAL
P12-REAL-TEST-BEFORE-DEPLOY
P12-REAL-DEPLOY-VERIFY
P12-REAL-FAILED-DEPLOY-RECOVERY
```

Disabled by default for normal customer profiles.

---

# 10. Phase 13 — Multimodal + web evidence

Goal: modern file/image understanding and controlled external/current research.

Route PDF/image/CSV/XLSX/etc. according to MIME and `ProviderProfile`: provider-native vision/file input where supported, extraction/OCR capability when emulated, explicit unavailable state otherwise.

Add `web.search`/`web.fetch` as evidence-oriented capabilities, not unrestricted browser control. Use external search when requested or local/runtime/Knowledge evidence is insufficient.

## Real gates — HARD

```text
P13-REAL-PDF
P13-REAL-IMAGE-OCR-OR-VISION
P13-REAL-PROVIDER-FEATURE-FALLBACK
P13-REAL-WEB-SEARCH
P13-REAL-WEB-CITATION
P13-REAL-WEB-INJECTION-BOUNDARY
```

---

# 11. Phase 14 — Additional surfaces and automation

Goal: reuse the same kernel outside interactive chat.

Potential surfaces:

```text
MCP
scheduled/recurring Assistant tasks
AI fields
record/context launchers
server-action/automation integration
```

Rules:

- same `CapabilityDefinition`/registry/policy/executor;
- same Context/Evidence contracts;
- surface-specific effective catalog allowed;
- unattended work has explicit identity/policy and stricter effects;
- interactive work receives scheduler fairness priority over bulk background work where necessary.

External references: OCA `ai_tool` explicitly targets reuse by MCP/native surfaces; Apexive exposes the same knowledge/tool concepts through Assistant and MCP. Reuse the single-registry pattern, not separate authority stacks.

## Real gates — HARD for every promoted surface

```text
P14-REAL-SURFACE-AUTHORITY
P14-REAL-SURFACE-CATALOG
P14-REAL-SURFACE-ACL
P14-REAL-SURFACE-EFFECT-POLICY
P14-REAL-SURFACE-RECOVERY
```

Recurring automation also requires repeated-run/no-duplicate evidence.

---

# 12. Phase 15 — Additional reasoning providers

Goal: prove provider-neutral design without forcing lowest-common-denominator behavior.

ProviderProfile from Phase 7 is required first.

Implement one API-backed provider, then a local provider only when it can deliver useful quality. Unsupported features remain explicitly `unavailable` or host-emulated.

Apexive's separate OpenAI/Anthropic/Mistral/Ollama provider modules are useful evidence that this separation is practical in Odoo; this project keeps a stricter common host decision/authority layer.

## Real gates — HARD per promoted provider

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

---

# 13. Domain Skill expansion rule

Sales/CRM/Accounting/Inventory do not wait for one monolithic final phase. After Phase 7 stabilizes extension contracts, domain Skills may be added as vertical packs whenever prerequisites for their behavior are complete.

Every pack needs semantic capabilities, context/evidence integration, permissions/policy, preview/verification for effects, agentic evals and named real gates.

Prefer high-value semantic operations over hundreds of shallow CRUD aliases.

Examples:

```text
Sales: quotation preparation / margin diagnosis / customer sales analysis
CRM: pipeline analysis / follow-up preparation
Accounting: receivable aging / customer account summary / invoice-state diagnosis
Inventory: shortage analysis / replenishment preparation
```

A pack cannot bypass a prerequisite: source-backed diagnosis needs Phase 8; mass import needs Phase 11; host changes need Phase 10.

---

# 14. Performance is cross-cutting

Keep Phase 0 timing points and extend them for context/retrieval/planning/scheduler/import/host work.

Every material phase/optimization compares representative simple + complex turns. Do not improve latency by weakening ACL, verification, recovery, provenance or by dumping unrestricted context/tools into the prompt.

Queue/concurrency measurements should include queue wait, admitted-running count, provider startup cost, fairness and server resource use. Capacity defaults are chosen from measurement, not copied blindly from OCA/Apexive or fixed forever at two slots.

---

# 15. Formal roadmap summary

```text
P0  baseline                                     COMPLETE
P1  provider boundary / decision loop            COMPLETE
P2  structured failures                          COMPLETE
P3  live public activity                         COMPLETE
P4  real answer streaming                        COMPLETE

P5  natural non-blocking multi-chat + continuity READY; P5.1 NEXT
P6  TaskPlan / multi-step EffectPlan / EffectJournal
P7  mini-framework + Assistant manifest
P8  Evidence + source/runtime/log intelligence
P9  company Knowledge / RAG
P10 Developer/Operator host operations
P11 advanced imports/artifact workflows
P12 controlled source-code modification
P13 multimodal + web evidence
P14 additional surfaces / automation / MCP
P15 additional providers
```

**Exact next action: begin P5.1 turn-scoped frontend/background state.**
