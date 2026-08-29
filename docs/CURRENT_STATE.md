# Current implementation state

Current product implementation lineage on `main`:

```text
Foundation/P0-P4 accepted through 8a4432dc9852eacc422b8c794b6613c75da702a9
P5.1 accepted through f7f924ce944db86e896745fef83ea2fb6fd6583a
P5.2 accepted through b4fbb034e113a41c26db77cb274f2b3b30f6eee3
P5.3 accepted through 32e836e7789ea72f3ba0d32fe6bdabbb092f5953
P5.4 accepted through 3e2b38d68fe172cd2cf92d7794159f73476ac23d
P5.5 accepted through 8427c8849b1e1f3afa6337de1209a6027410c266
P5.6 accepted through 720102f2a13af5240c779b07cc71ee65994a87b1
P5.7 model/reasoning preference sub-slice accepted through eb66e45447c4d64e1ebbb5e8322bffa759c12773
P5.7 complete through 074a71c29a6a6109ae7412e7b1f9850c4449e379
```

P5.6 and P5.7 are formally accepted. P5.7's conversation-scoped preference implementation passed
its focused, full regression, HOOT and real Codex/Chromium product-path gates. P5.8 is eligible but
not started. The exact live cursor is always `research/EXECUTION_STATE.md`.

## 1. Product/deployment baseline

- Odoo 18 Community, self-hosted Linux.
- Addon: `addons/odoo_ai_assistant`, version `18.0.10.19.0`.
- Embedded runtime; browser talks to Odoo, not a sidecar.
- Odoo/PostgreSQL own conversations, messages, turns, effect state, private working checkpoints and public events.
- Native `ir.cron` runs durable turns.
- Business authority is the originating effective user with `su=False`.
- Primary provider is local Codex App Server with one provider-owned host session consumed automatically by the installation. Odoo user/company authority remains isolated per turn.
- Product target remains one global general Assistant; see `PRODUCT_VISION.md`.

## 2. Host-owned agent loop

ADR-019/current code owns orchestration. The provider returns one strict `NextDecision` per call:

```text
final_answer
reasoning_capability_call
plan_step_proposal
```

Odoo resolves capabilities against the effective registry, validates inputs/policy/authority and executes REASONING calls only through `CapabilityExecutor` under the current user environment.

Provider decisions and bounded tool results/errors are persisted as private working items. Call identity, cancellation, budgets, restart handling and terminal state are host-owned. Provider protocol details are normalized/sanitized before becoming durable product state.

## 3. Current effect lifecycle

Accepted P5.5 path:

```text
one canonical PlanStepProposal
 -> prepare / preview / preconditions
 -> policy / approval
 -> revalidate
 -> durable write barrier
 -> execute under effective user
 -> verify
 -> authoritative verified-effect receipt
 -> provider continues with REASONING-only surface
 -> natural final answer
```

Post-effect continuation receives no PLAN catalog. A repeated plan proposal is rejected host-side, so provider continuation cannot execute the completed effect again.

Current limit: one canonical effect step. Bounded multi-step `EffectPlan` is P6 work.

## 4. Capability framework today

`CapabilityDefinition` is the atomic executable contract. Current metadata covers model-facing schema/description plus host-facing risk, effect, exposure, approval, configuration, groups, guards, budgets and optional preview/verification.

Core providers:

```text
assistant_preferences
odoo_query
odoo_actions
odoo_batch
odoo_runtime
```

`assistant_preferences` is the P5.7 host-owned conversation preference surface. Its autonomy mutation is approval-bound; response-language mutation is reversible and bounded. Neither creates Odoo/capability authority.

Settings can inspect and configure discovered definitions. Generic providers intentionally do not expose unrestricted ORM methods, SQL, Python, filesystem or shell.

Not implemented yet:

```text
external CapabilityProvider API
Skill/Bundle composition
first-class ContextProvider API
EvidenceProvider
EffectiveAssistantManifest
technical access profile
```

P5.6 adds conversation-context management at the current runtime seam; it does not pre-empt P7's general ContextProvider extension contract.

## 5. Conversation/context today — P5.6 and P5.7 accepted

Complete `odoo.ai.message` and `odoo.ai.turn` records remain history authority.

P5.6 adds immutable versioned per-turn `conversation_context_payload` checkpoints containing bounded:

```text
recent raw messages
rolling structured summary
active Odoo model/record references
evidence-reference slot
verified-effect references
conversation/session settings
```

Current v1 is built from durable **predecessor turn order**, not raw message creation order. This matters because Phase 5 permits Turn B's user message to be queued before Turn A's Assistant reply is persisted. The builder therefore:

```text
selects only same-conversation lower-id turns
requires causal predecessors to be terminal
reuses the newest predecessor checkpoint when available
folds terminal predecessor outcome/effect refs
rebuilds recent user/Assistant messages in causal turn order
excludes current and future turns
adds current bounded screen references
freezes the result for the turn
```

The provider port still uses the historical `conversation_summary: str` parameter to preserve the accepted provider-conformance seam. Its current product value is compact structured JSON, bounded to 8,000 characters.

Context remains data, never authority. ACLs, record rules, capability guards, policy, approval and effect execution are still re-evaluated host-side.

P5.7 adds stored conversation response-language preferences and snapshots the selected mode/fixed language on each durable turn before projecting them into `session_settings` alongside `odoo_user_language`. The same accepted slice adds an explicit temporary autonomy override on the conversation policy layer.

## 6. Queue, concurrency and settings

P5.2 accepted scheduler behavior includes:

- two physical `ir.cron` runner slots;
- logical capacity safely bounded to 1..2;
- short PostgreSQL advisory-lock admission/claim coordination;
- `READ COMMITTED` claim transaction;
- leases, cancellation and stale recovery;
- one active causal turn per conversation;
- cross-conversation concurrency;
- awaiting approval as causal blocker without consuming worker capacity;
- per-user fairness / anti-starvation ordering;
- wake-up after capacity release, cancellation and approval decisions;
- bounded administrator diagnostics.

The accepted P5.7 model/reasoning sub-slice promotes the execution-settings snapshot to v2:

```text
format_version
reasoning_model
reasoning_effort
autonomy_profile
policy
```

Legacy v1 snapshots remain readable. New turns capture the current per-user model and explicit provider-supported reasoning effort; `Predeterminado` stores no synthetic effort. Those selectors are immutable per turn. Revocable Odoo authorization, capability guards and provider availability remain dynamic.

The accepted P5.7 conversation slice additionally captures `response_language_mode` and `response_language` as immutable turn fields. Conversation autonomy is resolved into the already-existing per-turn policy snapshot, so later preference changes do not rewrite a queued turn's authority.

## 7. Frontend/product state

P5.1-P5.4 plus the accepted P5.7 model/reasoning sub-slice provide:

- per-conversation in-memory turn scopes rather than one global frontend execution lock;
- user can navigate/open another conversation while work continues;
- public activity separate from Assistant prose;
- provisional answer deltas separate from activity;
- one authoritative final Assistant message;
- explicit approval/failure/recovery presentation;
- no fake `Pensando…` bubble when real activity exists;
- provider-backed model families/variants in a nested Odoo dropdown;
- a reasoning-effort selector bounded by the effective model's advertised catalog;
- selectors that remain usable for future turns while another turn keeps its captured settings.

The new conversation preferences are intentionally chat-capability driven at this checkpoint; no extra frontend settings subsystem was introduced before the focused backend/runtime contract is validated.

Background scopes are still primarily web-client memory; P5.6 improves provider continuity through Odoo-owned turn context but does not by itself turn every frontend projection into durable UI state.

## 8. Failure/recovery

Phase 2 structured failures and P5.5 post-effect certainty remain authoritative.

Important rule: after the durable write barrier, uncertain outcomes are never treated as effect-safe blind retries. Provider failure after verified effect remains `effect_state=confirmed`.

## 9. Retrieval/RAG today

There is still no general embedded Evidence/RAG provider. The target remains hybrid rather than vector-only:

```text
live Odoo/runtime/schema/configuration
source/XML intelligence
logs/diagnostics
company Knowledge/files
lexical FTS
semantic/vector where evals justify it
web/external evidence later
```

P5.6 reserves bounded evidence references in the conversation-context schema, but no general evidence producer is claimed yet.

## 10. Technical operations today

Not currently exposed to reasoning:

```text
module install/update
odoo.conf modification
service/process restart
PostgreSQL administration
source-code modification
generic command execution
web search
```

Later privileged Developer/Operator operations require an explicit OS privilege boundary and specialized capabilities; autonomy alone cannot grant them.

## 11. Imports/artifacts today

Current batch capabilities are suitable for bounded controlled collections, not a mature thousands-row intelligent import workflow. A staged `DataImportSession` remains later work.

## 12. Formal roadmap state

```text
P0 COMPLETE
P1 COMPLETE
P2 COMPLETE
P3 COMPLETE
P4 COMPLETE
P5 IN_PROGRESS
  P5.1 COMPLETE
  P5.2 COMPLETE
  P5.3 COMPLETE
  P5.4 COMPLETE
  P5.5 COMPLETE
  P5.6 COMPLETE
  P5.7 COMPLETE
    model/reasoning sub-slice ACCEPTED
    conversation preference mutation ACCEPTED
  P5.8 ELIGIBLE_NOT_STARTED
P6+ NOT ELIGIBLE
```

Latest accepted P5.7 gates:

```text
P5-REAL-SESSION-POLICY       PASS
P5-REAL-LANGUAGE-PREFERENCE PASS
```

Implementation/validation record:

```text
research/P5.7_CONVERSATION_SCOPED_PREFERENCES.md
```

P5.8 may begin from its accepted target specification; it was not started in this run.
