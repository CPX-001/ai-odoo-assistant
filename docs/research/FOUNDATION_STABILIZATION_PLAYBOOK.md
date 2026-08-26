# Foundation stabilization playbook

Research date: 2026-08-26  
Inspected product baseline: `8c5bccdde6e1ca2c42c365386dd7f338c48a4c2b`  
Target: Odoo 18 Community / embedded runtime / Codex primary  
Status: execution guidance, not current-state authority

## Purpose

This is the **ordered implementation path** to follow before broad feature expansion.

The current product already has a valuable kernel: effective-user Odoo authority, durable turns, a capability registry/executor, bounded queries, controlled writes, approval/verification and an embedded Codex adapter. The next step is not a rewrite and it is not “add more RAG”. The next step is to make the critical turn path stable enough that adding one small feature does not repeatedly break chat, streaming, error handling or provider integration.

Use this document as a checklist. Do not start a later phase because it looks more interesting. A phase is complete only when its exit gate is satisfied.

---

# 1. What the current code actually does

The conclusions below come from the repository, not from the Project PDFs.

## 1.1 Current browser path is polling presented as streaming

The product submit path is patched by `assistant_panel_streaming_service.js`, which calls `streamAssistantChat()`.

`streamAssistantChat()` does not consume a browser SSE endpoint. It:

1. submits `/odoo_ai/v1/turn`;
2. polls `/odoo_ai/v1/turn/status` every 500 ms;
3. converts selected persisted event types into hard-coded Spanish text;
4. sends those strings through the callback named `onDelta`;
5. stores the concatenated strings in `state.streamingText`.

There is also a real SSE parser, `readAssistantStream()`, in the same module, with tests for fragmented text deltas and a terminal final event. It is not the transport used by `streamAssistantChat()`.

This means the current code has three concepts mixed under “streaming”:

- a generic SSE parser;
- turn-status polling;
- a fake assistant text stream made from progress labels.

They must be separated.

## 1.2 Current UI renders progress as if the Assistant said it

`assistant_panel.xml` renders `state.streamingText` inside an Assistant message bubble. If no text is present, it renders another Assistant bubble containing `Pensando…`.

Therefore even correct runtime events become conversational content instead of product activity state.

Target behavior must be two independent surfaces:

```text
ACTIVITY
  latest public operation
  expandable activity history

ANSWER
  provisional/final assistant text
```

Activity is not chat content and is not chain-of-thought.

## 1.3 Codex already emits the events needed for real text streaming

The current adapter accepts event families beginning with `item/agentMessage/`, but it only uses completed `agentMessage` items to build the final structured result.

The official Codex App Server protocol and Python SDK expose `item/agentMessage/delta` events. The official SDK example consumes those deltas directly while separately waiting for `item/completed` and `turn/completed`.

Therefore text streaming is not blocked by Codex lacking support. The missing layer is the adapter/host transport from Codex deltas to the browser.

## 1.4 The current Codex boundary is safer than it is compatible

`_validate_notification()` rejects any notification not explicitly allow-listed with `codex_event_not_allowed`.

That is fail-closed, but it means an additive App Server notification can break an otherwise valid turn. This is especially relevant because the Codex protocol evolves quickly.

The official Python SDK uses generated protocol models and can represent unknown notifications rather than requiring every additive notification to kill the run. At the same time, recent public Codex issues show that generated Python models can temporarily lag individual protocol fields/notifications.

Conclusion: **do not blindly replace the adapter with the SDK**. First build conformance tests. Then choose between:

- official SDK with its pinned matching runtime; or
- the current narrow adapter plus version-generated schemas and explicit forward-compatibility rules.

## 1.5 Provider errors are being flattened too early

The App Server itself exposes useful categories such as connection failure, response-stream disconnect, usage limit, unauthorized, bad request, sandbox failure and internal error.

The current adapter often collapses JSON-RPC/provider failures into broad codes such as `codex_provider_error` or `codex_turn_failed`.

The frontend loses more detail again. `submitStreamingAssistantRequest()` catches any thrown error and currently sets `service_unavailable`, regardless of whether the original cause was auth, protocol, timeout, tool error or context failure.

The user-friendly messages cannot be good while the structured diagnostic signal is destroyed before presentation.

## 1.6 Capability events exist, but they are too generic for the desired UX

`CapabilityExecutor` emits lifecycle events such as:

- `tool.started`;
- `tool.completed`;
- `tool.failed`;
- `tool.preview.started`;
- `tool.verify.started`.

The payload generally contains the capability name. The title is normally the static `CapabilityDefinition.title`.

That is a strong base. The missing piece is a **public activity projection** capable of safely saying what the host actually knows, for example:

- `Consultando res.partner`;
- `Leyendo esquema de sale.order`;
- `Buscando presupuestos abiertos`;
- `Preparando cambio en res.partner #42`;
- `Creando presupuesto para Azure Interior`;
- `Verificando 3 registros modificados`.

This should be derived from capability metadata + validated arguments + host results, not from private model reasoning.

## 1.7 Progress persistence and transaction visibility need explicit verification

Runtime capability events are emitted through the active Odoo turn environment. Queue-level events also have helpers that open separate cursors and commit independently.

Before implementing “live activity”, verify exactly which events become visible to the polling browser before the main turn transaction completes. Do not assume that because an event row was created in the worker cursor it is visible to another request immediately.

If runtime events are held until the turn transaction commits, real live progress requires a deliberately independent progress-write path. That path must not commit business writes early merely to make UI progress visible.

This is a P0 architectural detail because it determines whether polling can ever become genuinely live.

## 1.8 The provider is recreated for every turn

`CodexReasoningEngine.run_agent_turn()` starts a new `_CodexClient`; `_CodexClient.start()` launches `codex app-server`; the turn starts a new ephemeral Codex thread; the subprocess is then closed.

This provides strong isolation, but process startup + initialization + thread startup are paid on every request, including `hola`.

Do not optimize this by intuition. Measure its contribution first. If provider startup is a material fraction of simple-turn latency, evaluate a worker-local reusable App Server as a separate ADR decision. It would change the current “ephemeral per turn” invariant even though it would still remain embedded inside Odoo and not become a separate daemon.

---

# 2. External research conclusions that materially affect the plan

Only patterns that change a concrete decision are included here.

## 2.1 Codex Python SDK: compatibility is now a real option

Official Codex Python SDK findings:

- published as `openai-codex`;
- stable releases are documented;
- each SDK release pins a matching `openai-codex-cli-bin` runtime;
- `TurnHandle.stream()` exposes raw App Server notifications;
- generated public protocol types are available;
- text streaming is demonstrated with `item/agentMessage/delta`.

Implication for this project: the custom JSON-RPC client is no longer the only reasonable integration path.

Counter-evidence: public Codex issues have documented generated-Python gaps for newly added protocol events/fields. Therefore the SDK should pass project-owned protocol/conformance tests before becoming the product adapter.

## 2.2 Codex App Server has more actionable errors than the product currently preserves

App Server documents:

- bounded queues and overload error `-32001` (`Server overloaded; retry later.`);
- retryable backpressure with exponential backoff + jitter;
- `codexErrorInfo` categories such as context-window exceeded, usage limit, HTTP connection failure, response-stream connection failure/disconnect, unauthorized, bad request, sandbox error and internal error;
- version-specific JSON schema generation from the exact Codex executable.

Implication: provider failure normalization should use provider facts where available instead of turning all failures into `engine_unavailable`.

## 2.3 OpenAI Agents SDK reinforces a two-level stream

The Agents SDK explicitly separates:

- raw model stream events, useful for answer token deltas;
- semantic run-item events, useful for tool calls, tool outputs, approvals and other execution progress.

Implication: this product should not funnel progress through a callback called `onDelta`. Define answer-delta and public-activity channels separately even if both eventually travel through the same HTTP transport.

## 2.4 Odoo 19.4 validates intermediate status UX, but CPX can be more precise

Odoo documents intermediate statuses such as analyzing a request, consulting sources and preparing an action.

That validates the product pattern, but CPX owns more host-side detail than a generic status label. Because the capability host knows the validated model, operation and action lifecycle, CPX should expose **safe specific activity** when possible rather than stopping at generic `Analizando` labels.

## 2.5 Odoo AI Server Actions reinforce the Manager/Worker boundary

Odoo 19 documents the AI component as decision-maker and the tool as the code that applies business logic. Tool arguments must be explicitly configured for the AI.

CPX should keep its stricter version of this pattern:

```text
model proposes
  -> CapabilityDefinition schema
  -> host validation
  -> policy / approval
  -> trusted handler
  -> verification
```

Nothing in the streaming/error refactor requires weakening that boundary.

## 2.6 Pydantic AI supports the mini-framework direction but argues against premature token optimization

Current Pydantic AI capabilities can bundle instructions, tools, model settings and hooks; on-demand capabilities hide whole bundles until loaded. Its docs recommend using on-demand loading for distinct workflows and skipping it when a capability is used on most turns because the discovery round trip can cost more than it saves.

Its tool-search guidance also recommends keeping a handful of common tools eagerly loaded and deferring the long tail.

Implication for CPX:

- `CapabilityProvider -> Bundle/Skill -> CapabilityDefinition` remains a good conceptual direction;
- progressive disclosure should be added because catalog scale/evals require it, not because every token must be saved;
- common Odoo discovery/schema/query capabilities may remain eagerly available;
- safety bounds and cost budgets must be separate concepts.

## 2.7 OpenTelemetry is useful for naming, not as a dependency requirement

OpenTelemetry provides common error attributes such as `error.type`, exception attributes and standard trace/span concepts. GenAI semantic conventions continue evolving.

Implication: choose trace fields and error naming that can map naturally to OTel later, but do not make an observability backend a prerequisite for stabilizing the addon.

---

# 3. Ordering rule

The execution order is:

```text
0. Reproduce + measure
1. Stabilize provider boundary
2. Define failure contract
3. Make public activity truly live
4. Implement real answer streaming
5. Rebuild chat UX around activity + answer + failures
6. Attack measured latency
7. Harden regression/eval gates
8. Evolve capability mini-framework
9. Resume RAG/domain-feature expansion
```

Do not reverse phases 1-5. UI cannot reliably present state that the runtime does not model, and AI-generated error prose cannot recover diagnostic context already discarded by the backend.

---

# 4. Phase 0 — Create a reproducible baseline

Goal: stop debugging the assistant by impression.

Estimated size: small. Do this first.

## 4.1 Add a small scenario matrix

Create a repeatable local test/QA set containing at least:

- `hello`: no Odoo data needed;
- `read_partner`: find one known partner;
- `query_sales`: bounded `sale.order` query;
- `aggregate_sales`: one read_group path;
- `write_preview`: prepare a harmless partner update that requires approval;
- `write_execute_verify`: approve and verify it;
- `acl_denied`: limited user requests inaccessible data;
- `provider_auth_missing`;
- `provider_process_missing`;
- `provider_disconnect` or injected EOF;
- `provider_timeout`;
- `tool_invalid_input`;
- `tool_handler_failure`;
- `invalid_final_output`;
- `cancel_queued`;
- `cancel_running`;
- `worker_restart_before_write`;
- `worker_loss_after_write_barrier`.

These scenarios become permanent regression fixtures/evals.

## 4.2 Add per-turn timing points before optimizing

Record monotonic durations for:

```text
submit_received
turn_persisted
worker_claimed
runtime_started
provider_process_started
provider_initialized
provider_thread_started
provider_turn_started
first_provider_event
first_answer_delta
first_capability_started
last_capability_completed
reasoning_completed
result_persisted
browser_first_activity
browser_first_answer_delta
browser_final
```

Do not log prompt/tool content by default.

## 4.3 Record baseline results

For the scenario matrix, record at minimum:

- success/failure;
- normalized error code;
- total latency;
- queue wait;
- provider startup + initialize latency;
- time to first useful public activity;
- time to first answer delta where applicable;
- number of model turns/tool calls;
- input/output/cached token usage when available.

## Phase 0 exit gate

Do not start latency architecture changes until all of these are true:

- [ ] `hello`, one read, one action and one failure are reproducible.
- [ ] A turn can be decomposed into queue/provider/tool/finalization timing.
- [ ] The current 10-second-class simple-turn latency can be attributed rather than guessed.
- [ ] At least five important failure paths have observed original code + final UI code recorded side by side.

---

# 5. Phase 1 — Stabilize the ReasoningProvider boundary

Goal: make Codex evolution stop randomly breaking unrelated product code and freeze a contract that another provider could implement later.

Do **not** add another provider in this phase.

## 5.1 Define a provider-neutral contract from what the host actually needs

The port should cover concepts such as:

```text
ReasoningProvider
  health/config metadata
  run_turn(...)
    -> async ProviderEvent stream
  cancel(turn)

ProviderEvent
  answer_delta
  tool_call_requested
  provider_notice
  usage_updated
  completed
  failed
```

This is not a new agent framework. It is the transport/lifecycle port around the existing `AgentTurnService`.

Keep `CapabilityExecutor` and host authority outside the provider.

## 5.2 Build Codex protocol conformance tests before choosing SDK vs custom adapter

The same tests must be runnable against:

A. current custom App Server adapter;  
B. an experimental official `openai-codex` adapter.

Required cases:

- initialize succeeds;
- thread starts with the expected isolation settings;
- turn starts with output schema;
- `agentMessage` delta is accepted;
- completed agent message is accepted;
- dynamic tool request maps to the logical capability;
- capability success returns valid tool output;
- capability failure returns structured tool failure;
- additive/unknown non-critical notification does not fail the turn;
- malformed required event still fails closed;
- mismatched thread/turn/call id fails closed;
- cancellation interrupts the correct turn;
- provider terminal failure preserves structured error information;
- overload/backpressure is classified retryable without retrying unsafe host effects.

## 5.3 Decide the Codex implementation only after the conformance spike

Choose official SDK if it materially removes protocol code while preserving:

- dynamic tools;
- output schema;
- sandbox/read-only workspace isolation;
- ephemeral thread semantics;
- cancellation;
- provider-owned authentication;
- host-side tool authority;
- access to required raw/typed events.

Stay with the custom adapter if the SDK cannot preserve those requirements cleanly. If staying custom, generate/store protocol compatibility fixtures from the exact supported Codex version instead of hand-maintaining every notification shape.

## 5.4 Change forward-compatibility policy

Recommended rule:

- unknown **notification** with no authority/effect semantics: record sanitized diagnostic metadata and continue;
- unknown **server request** asking the host to perform work: reject;
- malformed known critical event: fail;
- identity mismatch (`threadId`, `turnId`, `callId`): fail;
- provider warning/rate-limit notice: surface as provider telemetry, not as turn failure unless the protocol says the turn failed.

This preserves host safety while making additive provider notifications less destructive.

## Phase 1 exit gate

- [ ] Provider conformance suite exists.
- [ ] Codex runtime/version compatibility is explicit and testable.
- [ ] Additive benign notifications no longer kill valid turns.
- [ ] Dynamic tools still execute only through `CapabilityExecutor`.
- [ ] Provider-specific code is confined behind one adapter/port.
- [ ] At least 100 repeated `hello`/simple-read turns do not show protocol-shape failures.

---

# 6. Phase 2 — Introduce a real failure contract

Goal: preserve facts from the failing component to the UI without exposing secrets or forcing robotic copy.

Do this before rewriting error messages.

## 6.1 Add one structured failure envelope

Recommended conceptual shape:

```text
FailureEnvelope
  code                 stable specific code
  category             broad product category
  stage                where in the turn it failed
  component            codex / queue / capability / retrieval / odoo / browser
  retryability         never | safe | after_change | unknown
  effect_state         none | not_started | confirmed | partial | unknown
  user_action          retry | reconnect | clarify | request_access | review | none
  safe_summary         short factual host-generated description
  safe_details         bounded structured facts
  diagnostic_id        support/debug correlation id
  provider_code        optional sanitized provider category
```

Do not use one string for all three jobs of machine routing, support diagnostics and user presentation.

## 6.2 Use a bounded category taxonomy

Start with categories that change recovery behavior:

- `input`;
- `context`;
- `authentication`;
- `provider_connection`;
- `provider_protocol`;
- `provider_capacity`;
- `provider_output`;
- `capability_discovery`;
- `capability_input`;
- `capability_execution`;
- `capability_output`;
- `policy`;
- `approval`;
- `odoo_access`;
- `retrieval`;
- `write_execution`;
- `verification`;
- `queue_worker`;
- `persistence`;
- `cancellation`;
- `internal`.

Do not create hundreds of public categories. Specificity belongs in `code`; product behavior belongs in `category` + `retryability` + `effect_state`.

## 6.3 Preserve Codex error facts

Map known App Server information where available, including:

- unauthorized;
- usage limit exceeded;
- HTTP connection failure/status;
- response stream connection failure;
- response stream disconnected;
- too many provider retry attempts;
- bad request;
- sandbox error;
- server overloaded;
- internal server error.

Never expose raw stderr, auth payloads or full upstream bodies to the browser.

## 6.4 Separate tool error returned to the model from failure shown to the user

A capability failure may be recoverable by the agent.

Model-facing tool failure example:

```json
{
  "ok": false,
  "error": {
    "code": "field_not_in_schema",
    "category": "capability_input",
    "retryable": true,
    "hint": "Inspect the current effective schema and choose an allowed field."
  }
}
```

User-facing presentation should normally wait until the agent either recovers or the turn becomes terminal.

## 6.5 Add a presentation layer, not a dictionary scattered across JS patches

Create one server- or shared-contract-level mapping from `FailureEnvelope` to a browser-safe failure view.

The UI should render:

- natural headline;
- what was affected;
- what the user can do next;
- whether any write may have happened;
- optional expandable technical detail: error code + diagnostic id.

## 6.6 AI-generated error prose is optional enrichment, never the source of truth

The desired copy can sound natural, but it cannot depend on the same provider that is currently unavailable.

Recommended policy:

- provider/auth/transport failure: deterministic natural presentation from structured facts;
- recoverable tool failure during a live agent turn: return structured failure to the model and let it adapt;
- terminal failure after model access is still healthy: optional model-generated explanation from a **sanitized FailureEnvelope**, validated against a small output schema;
- write effect `partial` or `unknown`: deterministic wording always takes precedence and must state uncertainty explicitly.

This avoids hallucinated explanations such as claiming a permissions problem when Codex actually disconnected.

## Phase 2 exit gate

- [ ] Original failure specificity survives backend -> turn -> browser.
- [ ] Frontend no longer turns every unknown thrown error into `service_unavailable`.
- [ ] Every terminal failure states `effect_state`.
- [ ] Retry buttons are driven by retryability, not generic UI guesswork.
- [ ] Provider unavailable/auth/timeout/tool input/ACL/write verification each produce distinct useful behavior.
- [ ] No raw secrets/provider stderr are exposed.

---

# 7. Phase 3 — Build public activity as a first-class protocol

Goal: show what the host is actually doing without exposing chain-of-thought.

## 7.1 Define `PublicTurnEvent`

Recommended shape:

```text
id / sequence
turn_id
kind
phase
status
label
resource
  model
  record_ids (bounded)
  display_names (optional bounded)
capability
progress (optional)
diagnostic_code (optional)
occurred_at
```

The browser must not infer meaning from arbitrary free text.

Useful event kinds:

```text
turn.queued
turn.started
provider.connecting
provider.connected
agent.answer.started
capability.started
capability.completed
capability.failed
retrieval.started
retrieval.completed
preview.started
preview.completed
approval.required
execution.started
execution.completed
verification.started
verification.completed
turn.completed
turn.failed
turn.cancelled
```

Avoid an `agent.thinking` event. The host cannot truthfully describe private reasoning.

## 7.2 Add capability-owned public activity descriptors

Extend the capability contract with optional presentation callbacks/metadata, conceptually:

```text
describe_public_call(context, validated_args)
describe_public_result(context, validated_args, result)
```

This must be trusted installed code and return a bounded structured description.

Examples:

`odoo.get_effective_schema({model: "sale.order"})`

```text
Leyendo esquema de sale.order
```

`odoo.query_records(...)`

```text
Consultando sale.order
```

A semantic business action can be richer:

```text
Preparando presupuesto para Azure Interior
Creando presupuesto S0421
Verificando presupuesto S0421
```

Generic capabilities should never invent a business name that was not validated/read from Odoo.

## 7.3 Make progress writes visible independently of the business transaction

First write an integration test proving whether current runtime events are visible to a separate status request while `run_turn()` is still executing.

If they are not, implement an independent public-event commit path that does **not** commit business effects.

Potential implementation direction:

- public event row committed in its own short cursor/transaction;
- event cursor independent from mutable turn-row state where necessary to avoid lock contention;
- final turn state remains authoritative;
- event write failure must not authorize or roll back business effects by itself.

Do not call `cr.commit()` inside the main business execution merely to make the UI look live.

## 7.4 Keep persisted activity bounded

Persist meaningful lifecycle events, not token deltas.

Good persistence:

- capability started/completed;
- retrieval source count;
- approval requested;
- write/verify lifecycle;
- failure category.

Bad persistence:

- every answer token;
- raw model reasoning;
- raw tool arguments/results;
- auth/provider internal payloads.

## Phase 3 exit gate

- [ ] A browser can observe at least one capability-start event before the final turn commits.
- [ ] Activity events identify real operations such as model/capability where safe.
- [ ] No public event contains chain-of-thought or secret values.
- [ ] Event cursoring works across multiple Odoo workers.
- [ ] Restart/reconnect can reconstruct the activity trail from persisted state.

---

# 8. Phase 4 — Implement real answer streaming

Goal: stream assistant answer text as answer text, not as progress labels.

## 8.1 Consume provider answer deltas

Map Codex `item/agentMessage/delta` into `ProviderEvent.answer_delta`.

Do not assume a streamed partial answer is authoritative final output. The existing final structured output/schema validation remains required.

## 8.2 Choose browser transport after the server event model works

Two viable options:

### Option A — Polling with ephemeral delta buffer

Keep short RPC polling and expose newly available answer chunks plus public events.

Advantages:

- least operational change;
- fits current durable turn/status architecture;
- reconnect naturally resumes by cursor.

Disadvantages:

- 500 ms granularity unless tuned;
- answer-delta storage/buffering must be designed carefully.

### Option B — SSE from Odoo

Use a dedicated browser -> Odoo SSE route for live answer/activity while durable turn state remains in Odoo.

Advantages:

- lower-latency push;
- natural token streaming.

Disadvantages:

- worker/proxy/timeouts/backpressure need production testing;
- Odoo worker must bridge events generated by a separate cron worker;
- still needs durable recovery when the SSE connection drops.

Decision rule: choose SSE only if polling cannot meet the measured UX target without ugly persistence/churn. Do not adopt SSE merely because an SSE parser already exists.

## 8.3 Keep answer stream and activity stream typed separately

Conceptual browser payload:

```text
answer.delta
activity.event
turn.final
turn.failure
```

Never append activity labels into `streamingText`.

## 8.4 Reconcile provisional stream with authoritative final answer

The provider currently returns a structured JSON final answer. Streaming raw `agentMessage` deltas may include the structured envelope rather than only the user-facing `answer` field depending on how output schema is emitted.

Test this against the exact supported Codex runtime before exposing raw deltas to users.

If deltas contain structured JSON rather than clean answer text, choose one of:

- a provider mode/event that streams the answer field cleanly;
- a small incremental structured-output parser with strict tests;
- delayed answer streaming while retaining live activity, if reliable field-level streaming is not possible.

Do not display half a JSON object as chat text.

## Phase 4 exit gate

- [ ] `hello` displays real answer text before final completion when the provider supports a clean stream.
- [ ] Activity never appears inside the assistant message bubble.
- [ ] Final validated answer replaces/reconciles provisional text without duplication.
- [ ] Disconnect/reconnect does not create duplicate assistant messages.
- [ ] Cancellation drains/terminates provider state correctly.

---

# 9. Phase 5 — Rebuild the chat UX around the correct state model

Goal: make the interface feel like an agent product rather than a debug panel.

Implement only after phases 2-4 expose reliable state.

## 9.1 Message layout

User message:

- render immediately;
- compact bubble/content width;
- do not reserve a giant empty assistant block.

Running turn:

```text
[small activity row]
Consultando sale.order                         ▾
```

Only the latest activity is visible by default.

Expanded:

```text
✓ Petición recibida
✓ Conectado a Codex
✓ Leyendo esquema de sale.order
✓ Consultando sale.order
• Verificando 5 resultados
```

Assistant answer:

- appears independently below/after activity;
- streams in place when available;
- no `Assistant: Pensando…` bubble.

## 9.2 Activity is a disclosure, not chain-of-thought

The expanded view may show:

- capability/tool names in a user-friendly form;
- Odoo model/resource;
- source type;
- approval/execution/verification lifecycle;
- durations where useful.

It must not show:

- model reasoning text;
- hidden prompts;
- raw args/results;
- auth material;
- stdout/stderr.

## 9.3 Failure UX

Failures should render as a dedicated compact card, not as a fake Assistant message.

Example:

```text
No pude completar la consulta
La conexión con Codex se cortó mientras esperaba la respuesta.
No se había iniciado ninguna modificación en Odoo.

[Reintentar]   Detalles ▾
```

For uncertain effects:

```text
El resultado de la acción no está confirmado
Odoo llegó a iniciar la ejecución, pero el worker se perdió antes de verificarla.
No voy a repetirla automáticamente.

[Comprobar estado]
```

## 9.4 Cancellation and steering

P0 UX: expose reliable cancel for queued/running turns.

Later, evaluate same-turn steering only if the Codex provider contract can support it without corrupting durable turn semantics. Codex App Server has steering concepts, but do not bolt them directly into the browser before host state/recovery semantics are defined.

## Phase 5 exit gate

- [ ] No hard-coded `Pensando…` Assistant bubble remains in the normal turn path.
- [ ] Latest real operation is visible in one compact row.
- [ ] Activity history is expandable.
- [ ] Answer and activity rendering are independent.
- [ ] Approval and failure are dedicated UI states.
- [ ] User can cancel a running turn and the UI reflects terminal cancellation.

---

# 10. Phase 6 — Optimize latency using measurements

Goal: make simple turns fast without sacrificing correctness.

## 10.1 Start with the measured largest component

Do not optimize token count first by default.

For `hello`, compare:

```text
queue wait
Codex process startup
initialize handshake
thread/start
model TTFT
generation
final schema validation
Odoo persistence
browser polling delay
```

Whichever dominates gets attacked first.

## 10.2 Low-risk latency work

Candidates that do not change architecture materially:

- remove duplicate runtime/account checks from the hot submit path;
- ensure `_trigger()`/cron pickup is measured and correctly configured;
- avoid rebuilding expensive static capability descriptors every turn if already safe to cache;
- cache deterministic provider/runtime detection for a short bounded period;
- reduce unnecessary browser poll delay after a turn has just been submitted;
- batch public progress writes;
- avoid serializing unused context;
- keep common capabilities eagerly available instead of introducing a discovery round-trip merely to save tokens;
- use batch Odoo operations instead of model-driven loops where appropriate.

## 10.3 Separate four kinds of budget

Replace the mental model “budget = save tokens” with four explicit concerns:

### Safety limits

Hard host bounds that prevent blast radius:

- maximum records written;
- maximum bytes;
- maximum unsafe/repeated effects;
- schema constraints;
- timeouts.

These remain strict.

### Exploration budget

How many read/retrieval/tool steps the model may use to solve the task.

This can be generous for safe read-only exploration.

### Cost budget

Provider/token/tool monetary policy. This may differ by provider/model/deployment.

### Latency budget

Stop conditions for work that is technically safe but no longer useful to wait for interactively.

A future remote paid provider can have a tighter cost profile without making Codex local behavior artificially timid.

## 10.4 Decide whether to reuse the Codex process only after profiling

If process startup + initialize is a material share of no-tool latency, prototype:

```text
Odoo worker
  -> one bounded reusable App Server client
     -> isolated ephemeral thread per Assistant turn
```

Requirements for the prototype:

- no shared workspace between users;
- no cross-user thread reuse;
- effective Odoo authority still entirely host-side;
- bounded idle lifetime;
- health check and restart on protocol failure;
- cancellation isolation;
- no auth leakage;
- concurrency test.

This changes ADR-016's per-turn subprocess assumption and therefore requires a superseding/amending ADR if adopted.

## 10.5 Initial performance targets

Targets should be refined after Phase 0. Reasonable product goals to start evaluating:

- submit persistence: p95 < 300 ms on local deployment;
- first public activity after worker claim: p95 < 500 ms;
- browser event propagation after commit: p95 < 750 ms;
- no-tool `hello` final: move materially below the current ~10 s observed experience;
- no-tool time to first answer delta: preferably < 3 s on a healthy provider, but treat provider/model latency as an external variable;
- no regression in action safety/recovery.

Do not turn these provisional targets into hard CI thresholds until deployment variance is understood.

## Phase 6 exit gate

- [ ] Simple-turn latency improvement is demonstrated with before/after measurements.
- [ ] The largest remaining latency components are known.
- [ ] No safety/ACL/write verification regression was introduced.
- [ ] Token/cost changes are measured rather than assumed.
- [ ] Any provider-lifecycle architectural change has an ADR and concurrency/restart tests.

---

# 11. Phase 7 — Build regression gates before adding major features

Goal: make “a tiny change broke half the chat” uncommon and immediately diagnosable.

## 11.1 Deterministic test layers

Maintain separate suites for:

### Provider contract

- protocol events;
- tool calls;
- cancellation;
- errors;
- version compatibility.

### Turn lifecycle

- queue/claim;
- leases;
- restart;
- final result;
- failure envelope;
- recovery.

### Capability host

- discovery;
- schema validation;
- availability;
- policy;
- preview;
- execute;
- verify.

### Browser protocol

- public event normalization;
- answer deltas;
- duplicate/reordered cursor handling;
- terminal final;
- failure presentation.

### UI

- latest activity;
- expanded activity;
- streamed answer reconciliation;
- cancel;
- approval;
- failure card.

## 11.2 Fault injection

Create deterministic injected failures at boundaries:

- EOF after initialize;
- EOF mid-answer;
- provider overload;
- malformed provider event;
- unknown benign notification;
- tool timeout;
- tool invalid output;
- ACL denial;
- verification failure;
- worker loss before/after write barrier;
- browser reconnect.

The expected result includes both terminal state and user-facing recovery action.

## 11.3 Agentic evals

Add a first permanent eval dataset of roughly 30-50 Odoo tasks covering:

- simple conversation;
- model discovery;
- query;
- aggregate;
- contextual record question;
- ambiguity/clarification;
- action preparation;
- approval;
- ACL denial;
- provider/tool failure recovery;
- custom-addon/source-grounding cases as those capabilities mature.

Score outcomes, not one exact tool sequence.

Track:

- task success;
- correct capability selection;
- invalid tool-call rate;
- evidence/grounding;
- clarification quality;
- unauthorized-write rate = 0;
- recovery correctness;
- latency;
- tool calls;
- tokens/cost.

## 11.4 Required gate for runtime changes

Any change to:

- Codex adapter;
- prompts/base instructions;
- capability descriptions/exposure;
- tool budgets;
- context assembly;
- retries;
- provider model settings

must run the relevant agentic regression subset in addition to deterministic tests.

## Phase 7 exit gate

- [ ] Failure injection covers the major boundaries.
- [ ] Provider/version regressions are caught before UI testing.
- [ ] A stable agentic eval dataset exists.
- [ ] Runtime changes can be compared by quality + latency + usage.
- [ ] A small chat change no longer requires manual testing of every failure mode.

---

# 12. Phase 8 — Evolve the capability host into the mini-framework

Goal: make the addon extensible like a small platform without replacing the safe kernel.

Start only after the critical path is stable enough to support extensions.

## 12.1 Keep `CapabilityDefinition` atomic

Do not replace the current definition with a weaker generic tool abstraction.

It remains the unit containing:

- stable identity/version;
- model-facing description and schemas;
- risk/effect;
- approval semantics;
- guards/dependencies;
- safety limits;
- preview/execute/verify behavior;
- public activity projection;
- trusted handler.

## 12.2 Introduce `CapabilityProvider`

Purpose: let trusted installed Odoo addons contribute capability definitions/bundles without editing `odoo_ai_assistant/runtime/capabilities/providers/`.

Provider contract should include:

```text
provider id/version
compatibility/API version
list definitions
list bundles/skills
availability/health diagnostics
```

Requirements:

- Odoo-installed/trusted code only;
- deterministic discovery;
- duplicate-id rejection;
- provider failure isolation;
- same executor/policy for every contributed definition;
- diagnostics can identify which provider supplied a capability.

Do not scan arbitrary Python packages from the host.

## 12.3 Introduce `CapabilityBundle / Skill`

A bundle is behavior/composition, not authority.

It may contain:

- stable id;
- description;
- domain instructions;
- selectors/references to `CapabilityDefinition`;
- context/activation hints;
- source/retrieval bindings later;
- provider/model preferences later if justified.

It must not contain a second handler registry or override host policy.

## 12.4 Model catalog lifecycle explicitly

Use vocabulary such as:

```text
discovered
  installed/trusted provider supplied it

available
  current deployment/user/context can use it

revealed
  model has been shown its contract

active
  current run/skill has selected/loaded it
```

Do not implement lazy loading for its own sake.

## 12.5 Progressive disclosure decision gate

Only add bundle/tool lazy loading when one or more are demonstrated:

- effective visible catalog grows large enough to hurt tool selection;
- input-schema tokens are a material part of latency/cost;
- evals show ambiguity between unrelated domain packs;
- remote providers have materially different cost constraints.

Common tools such as model discovery, schema and basic query can remain always available if evals show that is better.

This follows the useful part of Pydantic AI's guidance: defer the long tail, not everything.

## 12.6 Provider/model policy stays separate from capability policy

Prepare for future engines by defining a provider profile with facts such as:

- supports tool calls;
- supports structured output;
- supports answer streaming;
- context size;
- cost/usage reporting;
- parallel tools;
- model family/settings.

Do not create a lowest-common-denominator `ReasoningEngine` that hides valuable provider features. The host contract should support optional capabilities.

## Phase 8 exit gate

- [ ] A separate test addon can contribute one capability without modifying core registry lists.
- [ ] The contributed capability obeys identical ACL/policy/approval/verify behavior.
- [ ] One bundle can group existing definitions without duplicating handlers.
- [ ] Diagnostics identify provider/bundle/definition.
- [ ] Catalog lifecycle is testable.
- [ ] Progressive disclosure is either justified by evals or explicitly deferred.

---

# 13. Phase 9 — Resume product expansion

Only after phases 0-7 are complete and phase 8 is either complete or intentionally deferred.

Recommended expansion order:

## 9A. Retrieval/RAG

Build hybrid retrieval behind the same capability/evidence contracts:

```text
runtime/schema facts
source/XML/Python index
logs
document lexical/FTS
vector semantic retrieval
rerank/provenance
```

Do not make vector search the universal path.

## 9B. Semantic context hooks

Add compact model-specific context projections and semantic metadata before dumping more raw record data into prompts.

## 9C. Domain packs

Start with a few high-value semantic actions, probably Sales/CRM/Accounting depending on actual use.

Examples:

- prepare/confirm quotation;
- customer account summary;
- receivable aging;
- invoice state diagnosis;
- lead follow-up preparation.

Each becomes a capability with specific public activity and eval cases.

## 9D. Agent Profiles / Skills configuration

Expose bundles, sources and prompts to administrators once their underlying contracts are stable.

## 9E. Second provider

Only now implement a second reasoning adapter if there is a concrete use case. Its acceptance criterion is the same provider conformance + agentic eval suite, not “it can answer hello”.

---

# 14. Work that should NOT be done out of order

Until the relevant gates are passed, do not:

- add a large general vector RAG subsystem;
- add dozens of new business tools;
- import Pydantic AI as a second agent runtime;
- implement multi-agent routing;
- add a second provider only to prove provider neutrality;
- keep polishing the current `Pensando…` bubble instead of replacing the state model;
- create AI-generated error prose before preserving structured failure facts;
- make Codex long-lived before measuring startup cost;
- loosen capability/record safety limits merely to improve demos;
- implement progressive disclosure only to save small amounts of tokens;
- expose raw Codex events directly to OWL.

---

# 15. Suggested commit-sized work packages

These are intentionally smaller than the phases so work can remain reviewable.

## Package A — Baseline telemetry

- timing model/fields or bounded diagnostic spans;
- timing hooks in queue/runtime/provider/executor;
- scenario runner/report;
- no UX redesign.

## Package B — Provider events + error normalization

- `ProviderEvent` contract;
- richer Codex terminal/error mapping;
- benign unknown notification policy;
- conformance tests.

## Package C — Codex SDK spike

- experimental adapter only;
- same conformance suite;
- short decision note comparing code removed, compatibility, dynamic tools and lifecycle;
- either adopt or delete the spike.

## Package D — FailureEnvelope

- backend failure model;
- turn persistence/status projection;
- browser normalizer;
- failure matrix tests.

## Package E — Public activity schema

- typed `PublicTurnEvent`;
- capability activity descriptors;
- safe payload rules;
- integration tests.

## Package F — Live event visibility

- prove/fix independent progress transaction behavior;
- cursor/reconnect tests;
- no answer streaming yet.

## Package G — Real answer delta path

- provider answer deltas;
- server buffer/transport;
- browser typed events;
- final reconciliation.

## Package H — Chat activity UI

- remove fake Assistant progress messages;
- latest activity row;
- expandable trail;
- failure card;
- cancel state.

## Package I — Latency optimization

- optimize only measured top contributors;
- before/after report;
- ADR only if provider lifecycle changes.

## Package J — Eval harness

- scenario dataset;
- deterministic/fault injection;
- agentic graders/report.

## Package K — Provider/Bundle mini-framework

- extension contract;
- test provider addon;
- bundles;
- diagnostics;
- no lazy loading unless justified.

---

# 16. Definition of “foundation stable enough to expand”

Do not declare the base ready for major RAG/features until all are true:

## Reliability

- [ ] 100 repeated simple turns have no unexplained protocol failures.
- [ ] Browser reconnect does not duplicate final messages/actions.
- [ ] Provider additive notifications do not randomly break the product.
- [ ] cancellation/restart/recovery tests pass.

## Errors

- [ ] Connection, auth, provider stream, input, context, capability, ACL, action and verification failures remain distinguishable.
- [ ] User recovery action follows structured retryability/effect state.
- [ ] No generic copy falsely describes an unrelated cause.

## Streaming/activity

- [ ] User sees real current host operation.
- [ ] Activity trail is expandable and sanitized.
- [ ] Real answer streaming works where provider output allows it.
- [ ] No chain-of-thought is exposed.

## Latency

- [ ] Simple-turn latency is measured and materially better than the current experience.
- [ ] Time to first visible useful activity is short enough that the product never looks frozen.

## Safety

- [ ] Effective-user `su=False` invariant remains.
- [ ] No arbitrary ORM/SQL/shell execution was introduced.
- [ ] Writes still follow preview/policy/approval/execute/verify/recovery.
- [ ] Unauthorized-write rate remains zero in evals.

## Change safety

- [ ] Provider conformance tests exist.
- [ ] Fault-injection matrix exists.
- [ ] Agentic eval baseline exists.
- [ ] Runtime changes have a repeatable regression procedure.

Once these hold, RAG, Skills, domain packs and provider expansion become additive product work instead of more load on a fragile foundation.

---

# 17. Reference set used for this playbook

The Project PDFs remain useful background, but this playbook was re-derived from current code and current public references.

## Current repository

- `docs/CURRENT_STATE.md`
- `docs/CHAT_PRODUCT_FLOW.md`
- `docs/AGENT_RUNTIME_OPTIMIZATION.md`
- `docs/CAPABILITY_FRAMEWORK.md`
- `docs/adr/ADR-016-embedded-odoo-runtime.md`
- `docs/adr/ADR-017-addon-capability-framework.md`
- `addons/odoo_ai_assistant/runtime/agent/codex.py`
- `addons/odoo_ai_assistant/runtime/capabilities/executor.py`
- `addons/odoo_ai_assistant/models/turn_queue.py`
- `addons/odoo_ai_assistant/models/turn_event.py`
- `addons/odoo_ai_assistant/models/embedded_runtime.py`
- `addons/odoo_ai_assistant/static/src/services/assistant_stream_client.js`
- `addons/odoo_ai_assistant/static/src/services/assistant_panel_streaming_service.js`
- `addons/odoo_ai_assistant/static/src/services/assistant_panel_service.js`
- `addons/odoo_ai_assistant/static/src/components/assistant_panel/assistant_panel.xml`
- related Python/JS tests.

## External references checked 2026-08-26

### Codex

- App Server README / protocol/error behavior:  
  https://github.com/openai/codex/blob/main/codex-rs/app-server/README.md
- Python SDK README:  
  https://github.com/openai/codex/blob/main/sdk/python/README.md
- Python SDK FAQ/version-runtime relationship:  
  https://github.com/openai/codex/blob/main/sdk/python/docs/faq.md
- turn stream example using `item/agentMessage/delta`:  
  https://github.com/openai/codex/blob/main/sdk/python/examples/03_turn_stream_events/sync.py

### OpenAI Agents SDK

- streaming/raw vs semantic run events:  
  https://openai.github.io/openai-agents-python/streaming/
- tracing concepts:  
  https://openai.github.io/openai-agents-python/tracing/
- errors/exceptions:  
  https://openai.github.io/openai-agents-python/ref/exceptions/

These are architecture references only; the product does not need to adopt the Agents SDK.

### Odoo

- Odoo SaaS 19.4 AI Agents / Skills / Sources / intermediate status:  
  https://www.odoo.com/documentation/saas-19.4/es/applications/productivity/ai/agents.html
- Odoo 19 AI Server Actions / Manager-Worker separation:  
  https://www.odoo.com/documentation/19.0/es/applications/productivity/ai/server-actions.html

### Pydantic AI

- capabilities overview:  
  https://github.com/pydantic/pydantic-ai/blob/main/docs/capabilities/overview.md
- on-demand capabilities:  
  https://github.com/pydantic/pydantic-ai/blob/main/docs/capabilities/on-demand.md
- tool search/deferred loading:  
  https://github.com/pydantic/pydantic-ai/blob/main/docs/tools-advanced.md

These are composition/progressive-disclosure references. They are not a recommendation to replace the current runtime.

### OpenTelemetry

- semantic conventions:  
  https://opentelemetry.io/docs/specs/otel/semantic-conventions/

Use as naming/interoperability guidance; do not block product work on adopting an observability platform.

---

# 18. How to continue this playbook

When completing a package:

1. update the relevant checklist/gate here;
2. record the commit and measured result in a short `Progress log` entry below;
3. re-check `main` before starting the next package;
4. revise later phases if implementation evidence disproves an assumption.

Do not preserve a roadmap item merely because this document predicted it.

## Progress log

No implementation package from this playbook has been marked complete yet.
