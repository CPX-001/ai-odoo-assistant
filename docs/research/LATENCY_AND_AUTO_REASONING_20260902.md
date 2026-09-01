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

## External evidence used

Research was rechecked on 2026-09-02 against current public sources:

- OpenAI GPT-5.6 model guidance: Programmatic Tool Calling is recommended for bounded tool-heavy work that does not
  need fresh model judgment between steps; `low` is recommended for latency-sensitive workloads and higher reasoning
  efforts should be justified by representative evals.
  https://developers.openai.com/api/docs/guides/latest-model
- OpenAI GPT-5.6 builder guidance: move deterministic filtering/aggregation/orchestration into code to reduce latency,
  cost and context rot; lower reasoning efforts can retain strong quality.
  https://openai.com/index/builders-guide-to-gpt-5-6/
- Codex App Server protocol: initialization is connection-scoped, a thread contains turns, and the protocol supports
  multiple `turn/start` operations after one initialized connection. Reusing a client connection therefore does not
  require moving business authority into Codex.
  https://github.com/openai/codex/blob/main/codex-rs/app-server/README.md
- Anthropic tool-use guidance independently recommends parallel/combined execution for tool calls without data
  dependencies instead of unnecessary sequential model round-trips.
  https://docs.anthropic.com/en/docs/build-with-claude/prompt-engineering/prompt-templates-and-variables
- Odoo 18 performance guidance recommends recordset/batch operations and prefetch rather than per-record query loops.
  https://www.odoo.com/documentation/18.0/developer/reference/backend/performance.html

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

The lifecycle close is generic: `AgentTurnService` closes the first inner provider that exposes `aclose`, through the
existing provider-neutral wrapper stack. Codex-specific lifecycle stays in the Codex adapter.

### 2. Deterministic high-volume selection/deletion

Two capabilities were added behind the existing registry/executor:

- `odoo.query_record_ids`: schema-first, ACL/record-rule-aware selection of up to 500 ids without serializing fields
  that are not needed for the bulk effect;
- `odoo.records.bulk_delete`: 1..500 explicit ids, recordset-level access check and `unlink`, bounded preview sample,
  ALWAYS approval, irreversible effect classification and post-write absence verification.

The model still decides *which* records match the user's intent. The host now performs the mechanical large-record
operation once the exact bounded selection is grounded. For more than 500 targets, deterministic continuation remains
available, but the model no longer needs 50-record pages/chunks for ordinary hundred-record operations.

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

The chat reasoning picker now exposes `Auto` separately from `Predeterminado`. `Predeterminado` still means “let the
provider/model use its own default”. `Auto` is an Assistant host mode captured immutably on the turn; it is offered only
when the current model advertises at least `low`, `medium` and `high`, so the current Codex adapter can route all three
neutral tiers without inventing an unsupported provider value. This supersedes only the historical P5.7 note that Auto
had deliberately not yet been implemented; it does not rewrite the original P5.7 acceptance evidence.

## Validation methodology

The change should be promoted only after focused real measurements, not because fewer calls look better.

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

Compare the old 50+50+N query / 50-row write path with the new bulk selection path. Fewer provider decisions are only
a win if the same selection, ACL behavior, approval binding and verification remain correct.

Suggested provisional product targets for a healthy provider and a low-hundreds local Odoo operation:

- first useful public feedback: < 1 s from worker start;
- bulk target discovery: usually < 5 s of Odoo execution;
- prepared approval preview: target 10-30 s, investigate > 60 s;
- approval -> local execute+verify: normally seconds, with module hooks treated as workload-dependent.

Do not turn these into hard CI thresholds until enough deployment variance has been measured.

## Deferred optimizations

- Reuse the same Codex *thread* across NextDecisions only after an eval proves that incremental context is safe and
  avoids duplicate/stale host state.
- Parallelize independent host reads through a provider-neutral multi-call contract rather than adding Codex-only
  orchestration.
- Add selection handles if workloads regularly exceed the bounded id payload; do not expand ids indefinitely.
- Consider prompt-cache/persisted-reasoning controls only behind provider feature negotiation and measured gains.
