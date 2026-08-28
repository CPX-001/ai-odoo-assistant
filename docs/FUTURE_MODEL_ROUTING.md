# Deferred multi-model routing direction

Status: **deferred product idea; not an implementation commitment or active roadmap phase**  
Date: 2026-08-28

This note records a possible late-stage evolution of the provider-neutral Assistant. It exists only to avoid accidentally designing current contracts in a way that makes the idea unnecessarily expensive later.

It does **not** create current implementation work, validation debt or a new roadmap phase. The product should not begin multi-model routing until the core Assistant is mature, stable and measurably high quality across the existing roadmap.

## 1. Idea

A mature installation may eventually have several reasoning/inference models available at the same time, especially when running locally:

```text
fast text model
vision model
code-specialized model
large reasoning model
remote/API fallback
```

The user still interacts with **one Odoo AI Assistant**. The runtime may choose the most appropriate model for a whole task or, for genuinely separable work, delegate a typed subtask to a specialist model.

Potential routing inputs include:

```text
required modalities/features
skill/task type
quality requirement
latency
cost
local-vs-remote preference
privacy/data-egress policy
available RAM/VRAM/CPU/GPU
provider/model concurrency
current queue/load
```

The objective is not "more agents". It is to obtain useful local/private/cost-efficient operation without requiring one enormous universal model to perform every kind of inference.

## 2. Authority rule

Model routing must never create another authority stack.

```text
one Assistant / one host runtime
          |
          +--> selected main reasoning model
          +--> optional specialist inference models
          |
          v
same Context / Evidence / Capability / Policy / Executor authority
          |
          v
Odoo / host / external effects
```

A specialist model may return analysis, structured extraction, classification, image interpretation, code analysis or other typed evidence/subtask output. It does not receive independent Odoo/host effect authority merely because it is called a specialist agent.

Routing optimizes **who reasons**; it never changes **who authorizes**.

## 3. Prefer abstract requirements over model IDs

Do not bind normal capabilities or Skills directly to concrete model names such as `qwen-vl`, `llama-*` or a specific API model.

If model-aware execution is introduced later, consumers should express abstract requirements/preferences, for example:

```text
requires:
  vision: true
  structured_output: true

prefers:
  locality: local
  quality: high
  latency: normal
```

A future model-selection layer can resolve those requirements against actual configured models.

Concrete model identity/configuration belongs to provider/model configuration, not to the durable semantic meaning of `CapabilityDefinition`.

## 4. Possible late-stage contracts

Only if routing is actually justified, extend provider feature negotiation with concepts such as:

```text
ModelProfile
  provider
  model identity
  local | remote
  modalities/features
  context limits
  quality/specialization hints
  resource/capacity hints
  data-egress properties

ModelRequirements
  required features
  preferred traits
  minimum quality/policy constraints

ModelRouter
  choose an effective model from task + requirements + policy + current capacity
```

`ProviderProfile` remains about provider/runtime support. A future `ModelProfile` describes one selectable model within that provider/runtime.

These contracts are intentionally **not implemented now**. Their exact shape should be derived from the real providers/local runtimes available at that future point.

## 5. Routing levels

If implemented, add complexity gradually.

### Level 1 — configured main-model selection

Choose a model for the complete turn/task based on explicit configuration and feature support.

Example:

```text
simple text task -> fast local text model
vision request    -> vision-capable model
complex plan      -> stronger reasoning model
```

### Level 2 — deterministic/configurable router

Use host-owned rules/metadata to choose among configured models by features, privacy, cost, latency and capacity.

Prefer deterministic routing before adding another LLM merely to choose an LLM.

### Level 3 — specialist subtask delegation

Only for tasks that decompose naturally, for example:

```text
PDF extraction      -> document model
image interpretation -> vision model
Python/XML diagnosis -> code-specialized model
final integration    -> main reasoning model
```

Delegation should use typed task/result contracts and shared Evidence rather than free-form agents independently modifying Odoo.

### Level 4 — learned/agentic routing

A learned router, adaptive decomposition or more complex multi-model orchestration is optional research work. Adopt it only if evals show a material advantage over Levels 1-3.

## 6. Local runtime and capacity

Multiple local models introduce model-loading and GPU/RAM scheduling costs. The Assistant should not implement its own low-level GPU scheduler if Ollama, vLLM or the selected local runtime already owns model loading/eviction/concurrency effectively.

The Odoo Assistant scheduler should care about higher-level admission/backpressure facts, for example:

```text
model/provider available
estimated/requested capacity
concurrency limit
queue state
fallback allowed
```

This should integrate with the turn-scoped concurrency/backpressure architecture rather than create a second unrelated queue.

## 7. Privacy and fallback

Future routing may support policies such as:

```text
local_only
local_preferred
external_allowed
external_allowed_for_non_sensitive_data
```

A local specialist may fall back to an API model only when the effective policy permits the relevant data to leave the installation.

Provider/model failure or resource exhaustion must produce an explicit fallback decision or bounded failure; it must not silently send private data to a remote provider.

## 8. Minimal compatibility rules to preserve now

No routing subsystem needs to be built today. To avoid unnecessary future technical debt, current work should only preserve these lightweight rules:

1. Keep the reasoning boundary provider-neutral; Codex is an implementation, not the product contract.
2. Do not encode one concrete model ID into `CapabilityDefinition`/Skill semantics.
3. Keep selected model/provider values as turn-scoped snapshots so later routing cannot mutate a running turn retroactively.
4. Keep scheduler/resource capacity separate from reasoning/effect authority.
5. Keep model-produced specialist output on the data/evidence side of the authority boundary.
6. Avoid APIs that assume there can only ever be exactly one configured model for an installation.

If current implementation can satisfy these rules without new abstractions, **do not add new abstractions yet**.

## 9. When to reconsider implementation

Do not promote this idea merely because multiple providers/models are technically available.

Reconsider it only after the main product is effectively mature and at least one concrete need exists, such as:

- a customer wants a fully/local-mostly deployment;
- one local universal model is too slow or too resource-heavy;
- specialist vision/code/document models materially outperform the main model;
- API cost is material enough that routing has meaningful return;
- privacy rules require local processing for selected tasks;
- routing can improve throughput on real multi-chat workloads.

Before promotion, create comparative evals for task success, latency, resource use, cost, privacy compliance and routing accuracy. A router that saves compute but reduces task quality or complicates debugging without measurable benefit should not be retained.

## 10. Roadmap relationship

This idea is **post-maturity optional work**, conceptually adjacent to Phase 15 (`additional providers`) but not an exit criterion for Phase 15 and not a Phase 16.

The existing roadmap remains unchanged. No current `EXECUTION_STATE.md` cursor, gate or look-ahead rule is modified by this note.
