# Product vision — general Odoo agent

Status: current product direction; **not an implementation claim**.  
Date: 2026-08-28

This document defines the product the repository is intended to become. `CURRENT_STATE.md`, current code and accepted ADRs remain authoritative for what is implemented today.

## 1. Product thesis

`odoo_ai_assistant` is one global Assistant for the Odoo installation, not a collection of separate user-facing agents.

The target experience is comparable to using a capable coding/agent model directly against a real environment, but with an Odoo-owned authority layer between probabilistic reasoning and every operation that can read protected data, change state or touch the host.

The central rule is:

> **Restrict authority, not intelligence.**

The reasoning provider may analyze deeply, iterate, change hypotheses, retrieve more evidence, use many read-only capabilities when needed and produce answers as detailed as the user request warrants. The host decides what resources are visible, what operations exist, what permissions apply, whether approval is required, what effects are allowed and how success is verified.

```text
User
  |
  v
Odoo AI Assistant — one global conversational identity
  |
  v
Provider-neutral agent runtime
  |
  +--> dynamic context
  +--> evidence / retrieval
  +--> effective capabilities / skills
  |
  v
Odoo-owned authority and policy
  |
  +--> Odoo data/runtime/configuration
  +--> source/XML/logs/diagnostics
  +--> controlled host operations
  +--> knowledge sources and files
  +--> web evidence where allowed
  +--> future external connectors/surfaces
```

Codex is the primary provider now. The architecture must not make Codex the product contract; API-backed and local providers must be possible later without reducing the product to the lowest common denominator.

## 2. One Assistant, many skills

The product should expose one Assistant with global awareness of the installation. Domain or technical specialization is represented by Skills/Bundles and effective capability groups, not by forcing ordinary users to choose among independent agents.

Examples:

```text
Odoo AI Assistant
  +-- Sales skill
  +-- CRM skill
  +-- Accounting skill
  +-- Company Knowledge skill
  +-- Technical Diagnostics skill
  +-- Developer Operations skill
```

A Skill is composition and semantics. It may group instructions, capability selectors, context/evidence providers and configuration, but it does not create a second execution authority or bypass `CapabilityDefinition`.

## 3. Effective self-awareness

The Assistant must be able to answer questions such as `¿qué puedes hacer?`, `¿puedes revisar logs?` or `¿por qué no puedes instalar este módulo?` from real effective state rather than a hard-coded prompt.

The target projection is an `EffectiveAssistantManifest` derived from trusted host state, conceptually containing:

```text
provider and provider feature support
active technical/access profile
effective skills
effective/revealed capabilities
knowledge/evidence sources
context providers
installed Odoo/module/runtime facts needed for capability discovery
configuration state
known limitations / unavailable features and reason
```

The answer should describe what is available **now for this user/context**. It may also explain that a known feature is unavailable because it is disabled, not configured, not supported by the selected provider or forbidden by permissions. It must not claim capabilities merely because code exists somewhere in the repository.

Installing a trusted extension should be able to contribute a Skill/capability/source/context provider so that this manifest and the model-visible environment update without editing a central prompt or registry.

## 4. Capability model

`CapabilityDefinition` remains the atomic executable contract.

The desired extension hierarchy is:

```text
CapabilityProvider
  +-- Skill / Bundle metadata
  +-- CapabilityDefinition(s)
  +-- ContextProvider(s)
  +-- EvidenceProvider(s)
  +-- configuration schema/defaults
```

A normal provider author should describe one operation near its handler: name, human/model description, schemas, risk/effect, approval, guards, configuration, limits, preview/verification and optional public activity metadata. The framework derives reasoning, planning, diagnostics, Settings and future transport projections from that definition.

This is intentionally similar to documentation/schema generation from annotated functions: trusted code declares the contract once; consumers do not maintain independent copies.

### Large catalogs

When the catalog becomes large, the Assistant should retain high-level awareness while loading detailed tool schemas progressively.

```text
discovered -> available -> revealed -> active
```

Common discovery/query operations may remain eager. Long-tail domain or technical tools may be grouped under small Skills/namespaces and revealed on demand. Progressive disclosure is retained only when evals show equal or better task success/selection quality, not merely lower token use.

Current OpenAI Agents tool search/namespaces are a useful external pattern for this problem; they are not a runtime dependency.

## 5. Authority and access profiles

Two independent controls are required.

### Autonomy

Existing autonomy controls answer **how much confirmation is required**:

```text
Strict
Balanced
Autonomous
Full access
```

### Technical access profile

A separate profile answers **what classes of technical operation may exist for this user**.

Initial target profiles:

```text
Business/User
Developer/Operator
```

Internally this should be expressible through narrower host-owned scopes, for example:

```text
odoo.business
odoo.admin
odoo.source.read
odoo.source.write
host.logs
host.config
host.process
host.command
postgres.diagnostics
postgres.admin
```

Autonomy never creates permissions. `Full access + Business` is still not Developer access. Developer access still obeys capability policy, operating-system privilege boundaries and explicit high-risk controls.

## 6. The world the Assistant may eventually inspect

For a concrete installation the Assistant should be able, through explicit capabilities/evidence providers, to reason over all relevant layers:

- live Odoo business records;
- models, fields, schema and registry;
- menus/actions/views and XML inheritance;
- installed modules and dependencies;
- Python/addon source read access;
- Odoo configuration;
- Odoo logs and correlated tracebacks;
- PostgreSQL diagnostics/log evidence where operationally available;
- Odoo/host process and service state;
- company documents and uploaded knowledge;
- user-provided files and structured imports;
- web search/fetch when local evidence is insufficient and policy permits it;
- future external connectors.

Direct source modification is not an initial capability. It is a future Developer-only workflow that must stage changes, show diffs, test and deploy through an explicit controlled path rather than casually rewriting production code.

## 7. Context architecture

The Assistant has potential access to global installation context, but the model should not receive a global prompt dump.

Target pattern:

```text
small trusted BaseContext
  user/company/lang/timezone
  Odoo/database/version
  current screen/record/selection hints
  conversation state
  effective Assistant manifest summary

+ just-in-time ContextProviders
  module/runtime context
  model/view/action context
  relevant records
  configuration
  source/log/diagnostic context
  skill-specific context
```

The provider should be able to expand context iteratively as the task requires. A greeting should stay cheap. A diagnosis of a custom `sale.order` traceback may legitimately build a much richer context.

### Adaptive and deliberate resolution

The default mode is adaptive: start small and retrieve/inspect as needed.

A deliberate/Plan mode may be requested by the user or selected by an automatic strategy for complex work. It may create a host-visible high-level `TaskPlan` describing goals/subproblems and required evidence/tools before execution. This must remain distinct from an effectful `EffectPlan`.

`TaskPlan` is reasoning orchestration.  
`EffectPlan` is a host-authorized set of proposed effects.

Neither exposes private chain-of-thought.

## 8. Natural conversation and continuity

The Assistant should preserve provider-level conversational quality rather than behave like a workflow bot.

Required product behaviors include:

- natural general questions and detailed explanations without artificial short-answer limits;
- follow-ups such as `haz lo mismo con el mes anterior` or `esas no, solo las mías`;
- stable references to previously discussed records/evidence/results;
- clarification only when ambiguity materially prevents safe/correct work;
- explicit explanations when a feature is unavailable or permission-limited;
- after an action, a short natural synthesis of what happened, problems found and important caveats.

The durable conversation layer should therefore evolve beyond a fixed `last N messages` prompt into recent raw messages plus bounded structured conversation state/summaries/references.

Long-lived personal memory is not required for the initial target. Session/conversation preferences that affect behavior — for example `no vuelvas a pedirme confirmación para cambios normales en este chat` — should be represented as explicit conversation policy/settings bounded by administrator/system ceilings, not as an untrusted sentence hidden in history.

## 9. Non-blocking interaction and multi-chat concurrency

A running Assistant turn is background durable work. It must **not** become a global UI lock for Odoo, the Assistant panel or the user.

The target experience is:

```text
Chat A: turn running ---------------------> completes
        user switches away

Chat B: user reads history / changes model / sends another turn
                                             |
                                             +----> runs concurrently if capacity exists

Odoo: normal navigation/forms/dropdowns remain usable throughout
```

### Conversation-scoped busy state

`loading`/running state must belong to a turn/conversation, not to the entire Assistant panel.

While Chat A is running, the user must be able to:

- navigate normally in Odoo;
- close/reopen the Assistant;
- switch to Chat B/C;
- read other conversation history;
- create a new conversation;
- open model/autonomy/technical-profile selectors;
- change settings that are safe to change;
- submit work in another conversation when execution capacity allows;
- cancel/inspect the original background turn later.

Conversation history should expose compact running/approval/failure/completed state so background work is discoverable without forcing the user to remain in that chat.

### Snapshot semantics

A queued turn owns an immutable effective execution snapshot for settings that affect its behavior, such as selected reasoning model, effective policy/autonomy and relevant context/profile/config versions.

Changing the model/autonomy/profile while Turn A is already queued/running affects **future turns**, not Turn A retroactively. This prevents an unrelated UI change from changing authority or provider behavior halfway through execution.

Approval is different: it is an explicit state transition bound to the prepared effect and may resume the same durable turn.

### Ordering semantics

Parallelism is primarily **across conversations**.

By default, one conversation should preserve causal ordering: a new ordinary message should not race ahead of an earlier unresolved turn whose result is needed as conversation context. The initial target is therefore one active causal turn per conversation, with multiple conversations executable in parallel.

Future explicit steering/branching may allow interaction with a still-running conversation, but it requires its own semantics. It must not be approximated by silently starting two independent turns against the same conversation history.

### Capacity, fairness and backpressure

Concurrency is bounded by real server/provider capacity and configurable hard ceilings. The product should not promise unlimited parallel agents.

The scheduler must eventually account for:

```text
installation-wide concurrent turn ceiling
provider-specific concurrency/rate limits
Odoo cron/worker capacity
CPU/RAM/process cost
per-user fairness / anti-starvation
interactive vs future background-automation workload
```

When capacity is full, extra turns remain durably `queued`; the UI stays interactive and explains that work is queued rather than becoming disabled.

The scheduler must preserve exactly-once claim/lease/recovery semantics under concurrent workers. A browser polling/subscription failure must not cancel or own the server-side turn.

### Background event consumption

Turn execution is independent from the open browser. The UI may detach from a running turn and later resume from persisted status/live cursors.

The frontend should maintain turn-scoped state and may prioritize polling/subscription for the visible conversation while using lighter background updates/badges for other running turns. Transport choice (polling, bus/SSE later) is an optimization; durable turn state is authoritative.

## 10. Agent loop and effects

The current host-owned `NextDecision` loop remains the right foundation, but the product target is:

```text
reason
  -> inspect/retrieve/call read capabilities as needed
  -> optionally create/revise TaskPlan
  -> propose EffectPlan when effects are needed
  -> host prepare/preview/policy/approval
  -> execute + verify
  -> feed verified receipts/results back to reasoning
  -> continue reasoning if necessary
  -> natural final answer
```

Verification is new authoritative context, not necessarily the end of the conversation turn.

The target `EffectPlan` supports multiple bounded steps. Atomicity/recovery semantics must be explicit: Odoo-local operations that can share a transaction are different from segmented/external effects. The write barrier, verification and no-blind-retry principles remain mandatory.

## 11. Budgets

Budgets prevent loops and blast-radius growth; they must not become arbitrary intelligence limits.

Separate at least:

```text
SafetyBudget
  write steps / affected records / destructive or external scope

ExplorationBudget
  read/retrieval calls / replans / context expansion

CostBudget
  provider/token/cost envelope

LatencyBudget
  interactive execution envelope

ResponseBudget
  technical transport/storage bounds, not a preference for short answers
```

All must be configurable within hard host ceilings. A complex read-only investigation may legitimately use far more tool calls than a simple greeting or a destructive action.

Concurrency capacity/backpressure is an additional host resource budget; it must not be conflated with per-turn exploration limits.

## 12. Evidence and retrieval

Retrieval is broader than vector RAG. The primary target is installation-specific intelligence, with company Knowledge as an important configurable layer.

```text
Evidence layer
  +-- LIVE
  |     Odoo records
  |     runtime/schema/configuration
  |     logs/diagnostics
  |     PostgreSQL/host diagnostics
  |
  +-- STRUCTURED/INDEXED
  |     Python/XML/source index
  |     company documents
  |     attachments/Knowledge
  |     lexical FTS
  |     semantic/vector index where evals justify it
  |
  +-- EXTERNAL
        web evidence
        future connectors
```

All providers should normalize to a shared `Evidence` contract carrying provenance, locator, trust, freshness/fingerprint, bounded data/excerpt, access scope and citation metadata.

### Agentic hybrid retrieval

The host supplies small reliable context automatically. The reasoning provider chooses when to search deeper and may perform several retrieval steps. The host may require evidence for assertions/operations that must be installation-specific or safety-critical.

There is no mandatory vector-search call before every message.

### Live business truth

Frequently changing Odoo business records should normally be queried live through capabilities rather than indexed as the authoritative RAG corpus. Indexing is better suited to documents, source structure and other corpora whose freshness/invalidation can be controlled.

### Evidence policy

Evidence priority depends on the question. Runtime/source/configuration generally outrank generic documentation for `what does this installation do?`; official documentation can be a sensible first source for `where is the standard Odoo option?`, followed by installation verification where needed.

## 13. Knowledge product

The product should provide an Odoo-native Knowledge/Sources area supporting at least uploaded files and managed sources.

Target lifecycle:

```text
uploaded/discovered -> processing -> indexed -> active
                                \-> error
```

The Assistant should also be able to accept a file in chat and, when authorized, create the Knowledge Source, extract it, segment it coherently, index it and report the result.

Start with deterministic extraction/structure + PostgreSQL lexical/FTS retrieval where appropriate. Add embeddings/vector/hybrid ranking only when evals show meaningful recall/answer-quality gains. Large files should be processed in bounded jobs/chunks rather than inserted wholesale into model context.

## 14. Logs and diagnostics

Logs are evidence, not a raw prompt dump.

A diagnostic provider should support time/component/severity/context-aware search and bounded surrounding reads. A request such as `analiza el último error que me dio Odoo al confirmar este pedido` should correlate screen/record/action/time and candidate tracebacks instead of blindly selecting the literal final log line.

The same principle applies to PostgreSQL and host diagnostics.

## 15. Host operations

The long-term Developer/Operator experience includes controlled operations such as:

- inspect/install/update Odoo modules;
- inspect/modify selected Odoo configuration;
- inspect/restart approved services/processes;
- run bounded diagnostics;
- potentially execute console-style commands through an explicit Developer-only capability.

The normal Odoo process should not simply become root. Operations requiring privilege elevation need an explicit host privilege boundary/broker/allowlist and an ADR before implementation.

Prefer high-level tested capabilities such as `odoo.module.update` or `odoo.config.patch` over generic shell where they cover the use case. A generic command capability, if later introduced, is a high-risk fallback with dedicated sandbox/policy/audit requirements.

## 16. Advanced data operations and artifacts

Mass data work is a first-class workflow, not thousands of individual model-authored CRUD calls.

A future `DataImportSession` should support:

```text
file/attachment
  -> inspect columns/types
  -> choose model/schema
  -> map fields
  -> validate rows
  -> detect duplicates/problems
  -> propose bounded corrections/enrichment
  -> preview
  -> approval where required
  -> chunked ORM execution
  -> per-row/aggregate receipts
  -> final synthesis
```

CSV/XLSX/PDF/images should be routed through appropriate parsers/OCR/vision depending on provider feature support.

## 17. Effect journal and recent reconstruction

Assistant-produced effects should have a bounded recent operation journal suitable for diagnosis and reconstruction, not an infinite database backup.

For a configurable short retention window it may store the minimum snapshots/receipts needed to answer:

- what did the Assistant modify/delete/import?;
- what was the verified resulting state?;
- can a safe inverse operation be prepared?;
- can a deleted record be reconstructed approximately from retained data?

The contract must distinguish `reversible`, `reconstructable`, `irreversible` and `external/unknown`. Deleting a record is not automatically a true undoable operation merely because some field values were captured.

## 18. Multimodal and web

The product target includes file, image and document understanding comparable to modern agent products.

Provider feature negotiation determines whether vision/file handling is `native`, `emulated` through an OCR/extraction capability, or `unavailable`.

Web access is evidence-oriented search/fetch, not unrestricted browser control. It should normally be used when local Odoo/runtime/company evidence is insufficient or the question is explicitly external/current.

## 19. Provider-neutral feature negotiation

Do not force all providers to the least capable common subset.

Each provider exposes a sanitized feature profile, conceptually:

```text
structured_output: native | emulated | unavailable
tool_calling:      native | emulated | unavailable
answer_streaming:  native | emulated | unavailable
vision:            native | emulated | unavailable
file_input:        native | emulated | unavailable
web:               native | emulated | unavailable
large_context:     native | emulated | unavailable
```

The effective product feature is the intersection of product support, provider support, configuration and user/policy authority. The Assistant manifest should be able to explain unavailable features.

Provider concurrency/backpressure characteristics also belong to the runtime feature/capacity profile; they must not be guessed from the provider name.

## 20. Additional surfaces

Chat is the primary product surface, not a separate authority model.

Future MCP, scheduled automations, AI fields or context launchers must reuse the same `CapabilityDefinition`, registry, policy, executor, evidence contracts and effective-user/technical-profile semantics. Each surface may reveal a different effective catalog according to its context, but it must not create a parallel tool registry.

Recurring Assistant work may use native Odoo scheduling/queue primitives where appropriate. Server-level recurring operations are a distinct host capability class even if both are initiated conversationally.

Future unattended/background work must coexist fairly with interactive chat capacity rather than starving user-facing turns.

## 21. External references and deliberate differences

External systems are references, not requirements:

- Odoo 19 AI separates Tools from indexed Sources and makes tool availability depend on installed applications. This supports keeping executable capability and knowledge/evidence concepts distinct.
- Apexive `odoo-llm` demonstrates useful breadth: hybrid knowledge retrieval/citations, providers, domain tools and MCP reuse. This project should match useful functionality without copying parallel authority or exposing framework complexity to normal users.
- OpenAI Agents tool namespaces/deferred loading validate progressive disclosure for large catalogs. This project keeps its Odoo-owned runtime/authority rather than adopting another runtime wholesale.
- Codex products demonstrate that long-running agent work can live in independent threads while the user switches to other tasks. The product target adopts the multi-tasking principle while preserving Odoo-owned durable turns and host authority.

The intended product difference is a **single deeply integrated Odoo agent with broad intelligence and tightly governed authority**, not merely a chatbot or generic AI framework embedded in Odoo.
