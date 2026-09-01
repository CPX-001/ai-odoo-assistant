# Latency, deterministic bulk work and Auto reasoning — 2026-09-02

Status: implementation checkpoint; focused real-environment validation still required. This note does not alter the
Phase-7 acceptance cursor or convert any blocked provider gate into PASS.

## Problem observed

A real deletion-preparation turn needed more than three minutes while repeatedly reading 50-record pages and staging
50-record mutation chunks. Current code confirmed two independent amplification factors:

1. the host-owned `NextDecision` loop correctly asks the provider for one decision at a time, but the Codex adapter
   launched and initialized a new `codex app-server` process for every decision;
2. deterministic paging/chunking limits were pushed back through the model even when no fresh judgment was needed.

The safety model is not the problem and is preserved: Odoo remains authority, reads/writes use the effective user with
`su=False`, and effects remain preview -> policy/approval -> barrier -> execute -> verify.

The high-volume case is an optimization signal, not the expected normal chat workload. Ordinary chat should remain
optimized first for short answers, a few grounded reads, and bounded business actions. Large imports or spreadsheet
work are a different product shape and must not be forced through an ever-growing collection of bulk-record shortcuts.

## External evidence used

Research was rechecked on 2026-09-02 against current public sources:

- OpenAI GPT-5.6 model guidance: Programmatic Tool Calling is recommended for bounded tool-heavy work where code can
  reduce several or large intermediate results by filtering, joining, ranking, deduplication, aggregation or
  validation. Multiple/parallel/dependent calls alone do **not** justify programmatic execution; direct calls remain
  preferable when results are small, may change the next model decision, require approval, or must preserve native
  artifacts/citations.
  https://developers.openai.com/api/docs/guides/latest-model
- OpenAI Agents SDK separates two concerns that should also remain separate here: whether the model may emit multiple
  tool calls in one provider turn (`parallel_tool_calls`) and how the local runtime executes those calls
  (`max_function_tool_concurrency`). Approval/input guardrails remain runtime-owned and are revalidated before
  execution.
  https://openai.github.io/openai-agents-python/ref/model_settings/
  https://openai.github.io/openai-agents-python/ref/run_config/
- OpenAI Agents SDK tool search uses namespaces/deferred loading instead of sending an indefinitely growing flat tool
  catalog. This is relevant to the existing Phase-7 progressive-disclosure framework if/when evals justify activating
  it; it is not a reason to introduce the SDK as a dependency.
  https://openai.github.io/openai-agents-python/tools/
- Codex App Server protocol: initialization is connection-scoped, a thread contains turns, and the protocol supports
  multiple `turn/start` operations after one initialized connection. The same protocol documents connection-level
  subscriptions and `thread/status/changed` notifications, so a reused connection must isolate late notifications from
  a completed old thread instead of applying the next thread's identity checks to them.
  https://github.com/openai/codex/blob/main/codex-rs/app-server/README.md
- Anthropic independently recommends issuing independent tool calls together and keeping dependent calls sequential;
  parameters must never be guessed merely to force parallelism.
  https://docs.anthropic.com/en/docs/build-with-claude/prompt-engineering/prompt-templates-and-variables
- Odoo 18 performance guidance recommends recordset/batch operations and prefetch rather than per-record query loops.
  https://www.odoo.com/documentation/18.0/developer/reference/backend/performance.html
- Odoo's own import product separates file ingestion, column-to-field mapping, validation (`Test`) and final import,
  and supports `.xlsx` and CSV across business objects. That separation is a useful future product pattern for chat
  file imports.
  https://www.odoo.com/documentation/18.0/applications/essentials/export_import_data.html

These references support the methodology, not a dependency choice. The implementation remains inside the existing
provider/capability boundaries.

## Implemented architecture

### 1. Turn-scoped provider transport reuse

`ReusableCodexDecisionEngine` keeps one App Server process/initialized stdio connection for the sequence of provider
decisions made by one `AgentTurnService` run. Each decision deliberately starts a fresh ephemeral Codex thread and
receives the complete host-authored bounded working state.

This first step removes repeated process + initialize overhead while preserving the current durability rule:
provider thread history is never business state. Reusing one Codex thread and incremental context is intentionally
left for a later eval because it changes context/caching semantics more substantially.

Because App Server subscriptions may deliver thread lifecycle/status notifications after `turn/completed`, the reusable
adapter remembers only successfully completed provider thread/turn ids and filters their later notification-only frames
before validating the next decision. JSON-RPC server requests (frames with an `id`) are never filtered and still fail
closed on this provider boundary.

The lifecycle close is generic: `AgentTurnService` closes the first inner provider that exposes `aclose`, through the
existing provider-neutral wrapper stack. Codex-specific lifecycle stays in the Codex adapter. The active streaming path
also preserves the existing interactive Stop/redirect proxy; session reuse must not trade latency for loss of live turn
control.

### 2. Deterministic high-volume selection/deletion

Two capabilities were added behind the existing registry/executor:

- `odoo.query_record_ids`: schema-first, ACL/record-rule-aware selection of up to 500 ids without serializing fields
  that are not needed for the bulk effect;
- `odoo.records.bulk_delete`: 1..500 explicit ids, recordset-level access check and `unlink`, bounded preview sample,
  ALWAYS approval, irreversible effect classification and post-write absence verification.

The model still decides *which* records match the user's intent. The host performs the mechanical large-record
operation once the exact bounded selection is grounded. These capabilities are a narrow fast path for an uncommon
large exact selection. They are **not** the future spreadsheet-import architecture and should not grow into one.

A follow-up cleanup removed their names and routing rules from the Codex transport adapter. Provider adapters should
own transport/protocol translation, not business/tool selection. Capability descriptions, Skills and the host catalog
are the provider-neutral places for that guidance.

### 3. Provider-neutral Auto reasoning router

`reasoning_effort.py` introduces neutral `light | balanced | deep` tiers. It does not know Codex effort tokens.

The route uses:

- the existing bounded 0..8 structural complexity score;
- explicit deliberate Plan mode;
- capability results/errors already requested by the model;
- multiple staged effects;
- user redirects.

This is intentionally hybrid without a second LLM router call: the host chooses a cheap initial tier, then the model's
own prior neutral decisions become evidence that can escalate later decisions. The Codex adapter maps the neutral tiers
to `low | medium | high`. A future provider can map the same neutral tiers differently.

The chat reasoning picker exposes `Auto` separately from `Predeterminado`. `Predeterminado` means “let the
provider/model use its own default”. `Auto` is an Assistant host mode captured immutably on the turn; it is offered only
when the current model advertises at least `low`, `medium` and `high`, so the current Codex adapter can route all three
neutral tiers without inventing an unsupported provider value.

### 4. Common-path turn-stable host projection cache

Multi-step chat turns were also repeating work unrelated to provider reasoning. `AssistantExtensionDecisionEngine`
used to re-resolve the current Odoo view, parse its XML, inspect field labels, recompute configuration health and rebuild
the Assistant manifest before every provider decision.

The wrapper is already turn-scoped, so it now memoizes only host projections whose inputs are stable for that turn:

- enriched current-screen semantics;
- sanitized capability/configuration health;
- the derived provider-facing Assistant manifest.

The cache key includes the turn/environment, screen payload, model-visible capability names and the capability/Skill/
ContextProvider enablement overrides that can change the projection. Returned cached structures are copied rather than
shared mutably.

JIT `ContextProvider` contributions deliberately remain **uncached** and are collected for every decision. A provider
may expose time-sensitive installation/runtime evidence, so saving a small amount of Python/Odoo work is not allowed to
silently turn JIT context into stale state.

This optimization targets the normal product path (a few iterative reads/reasoning steps), not only bulk operations.

## Next optimization direction: model-side grouping, host-side execution policy

The strongest common next step is to reduce avoidable provider round-trips when the model already knows that several
READ calls are independent. Mature runtimes separate two contracts:

```text
model emission policy
    -> one call or several independent calls in one model turn

host execution policy
    -> serial / bounded-concurrent execution chosen by the runtime
```

The project should preserve that separation. In particular, “the model emitted calls together” must **not** mean “run
Odoo ORM calls concurrently on the same cursor”. An initial provider-neutral multi-call contract can execute independent
Odoo reads serially in model order while still saving provider round-trips. Actual execution concurrency should be a
separate host decision, enabled only for capability classes whose runtime semantics make it safe and useful.

Writes, approval-bearing operations and calls whose arguments depend on earlier results should remain direct/sequential.
This follows both OpenAI's and Anthropic's current tool-use guidance and fits the existing host-authority model.

Do not implement a second generic meta-tool that accepts arbitrary capability names/arguments. Multiple-call support,
if promoted, belongs in the `NextDecision`/host loop so every nested call still passes the same registry/schema/policy/
budget/executor boundary.

## Future spreadsheet/file import architecture

A future prompt such as “importa este Excel” should not be implemented by raising the normal chat batch limit or by
adding a chain of format-specific CRUD shortcuts. Treat the uploaded file as an artifact/evidence source and separate
semantic decisions from row mechanics:

```text
uploaded artifact
  -> bounded file/type inspection
  -> tabular parse + column/sample profile
  -> model proposes column/relationship mapping
  -> host resolves effective Odoo schema + permissions
  -> deterministic row validation/normalization
  -> preview: creates / updates / rejects / ambiguities
  -> policy + approval
  -> bounded import execution using Odoo recordset/batch semantics
  -> verification + row-level outcome artifact
```

The model is useful for ambiguous column meaning, relationship intent and business interpretation. Parsing thousands of
cells, validating primitive types, chunking database work and collecting row errors are deterministic host jobs.

The executable import step should still be a `CapabilityDefinition` (or a small family of typed import capabilities)
using the same policy/approval/executor/verification infrastructure. File/artifact parsing should be reusable evidence
infrastructure, not embedded inside the Codex adapter and not a parallel action framework. Where Odoo already has
stable import semantics worth reusing, wrap the safe bounded behavior rather than exposing arbitrary import/ORM methods.

This keeps today's normal chat lightweight while leaving a clean path for CSV/XLSX, attachments and later structured
artifacts without duplicating security or mutation logic.

## Validation methodology

The changes should be promoted only after focused real measurements, not because fewer calls look better.

For the original deletion-style scenario record at minimum:

- total turn latency to approval preview;
- provider decision count;
- App Server process starts per host decision loop (target: 1);
- process initialize duration;
- per-decision duration;
- capability execution duration;
- selected Auto tier/effort per decision;
- records selected/deleted and exclusion correctness;
- approval count;
- post-delete verification;
- final answer consistency with prepared/executed state.

For normal chat, add representative one-read, two-dependent-read and several-independent-read scenarios. Record
provider decisions separately from capability executions so a future grouped-read optimization can prove that it
reduced model round-trips without hiding extra Odoo work.

Suggested provisional product targets for a healthy provider and a low-hundreds local Odoo operation:

- first useful public feedback: < 1 s from worker start;
- bulk target discovery: usually < 5 s of Odoo execution;
- prepared approval preview: target 10-30 s, investigate > 60 s;
- approval -> local execute+verify: normally seconds, with module hooks treated as workload-dependent.

Do not turn these into hard CI thresholds until enough deployment variance has been measured.

## Deferred optimizations, ordered by expected product value

1. Provider-neutral grouping of genuinely independent READ calls, with host execution policy kept separate. Start with
   serial Odoo execution and measure the saved provider round-trips before introducing runtime concurrency.
2. Reuse the same Codex *thread* across `NextDecision`s only after an eval proves that incremental provider context is
   safe, restartable from Odoo durable state and does not duplicate/stale host evidence.
3. Activate progressive disclosure only when the existing disclosure eval shows that tool-selection quality and latency
   improve. Prefer namespace/Skill/bundle-level discovery over a second registry.
4. Add artifact/file ingestion when file-input work enters scope; design it once for CSV/XLSX/attachments rather than
   stretching the rare bulk-delete path into an import system.
5. Add selection handles only if real workloads regularly exceed bounded id payloads. Do not pre-build an unbounded
   selection subsystem for a case the chat rarely needs.
6. Consider provider-specific prompt-cache/persisted-reasoning controls only behind provider feature negotiation and
   measured gains.
