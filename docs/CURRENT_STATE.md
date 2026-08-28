# Current implementation state

Runtime state revalidated on 28 August 2026 against implementation baseline `24b9460ad09998ec50d853e0a715b543e5991bbb`. Documentation commits after that baseline do not themselves create runtime features.

This document distinguishes **implemented code** from **formal roadmap acceptance** and from the target in `PRODUCT_VISION.md`.

## 1. Product/deployment baseline

- Odoo 18 Community, self-hosted Linux.
- Addon: `addons/odoo_ai_assistant`, version `18.0.10.10.0` at the audited runtime baseline.
- Embedded runtime; browser talks to Odoo, not a sidecar.
- Odoo PostgreSQL owns conversations/messages/turns/effect state/live public events.
- Native `ir.cron` runs durable turns.
- Business authority is the originating effective user with `su=False`.
- Primary provider is local Codex App Server with provider-owned authentication.
- Product target is one global general Assistant; see `PRODUCT_VISION.md`.

## 2. Host-owned agent loop

ADR-019/current code owns the active orchestration path.

The provider returns one strict `NextDecision` per provider call:

```text
final_answer
reasoning_capability_call
plan_step_proposal
```

Odoo resolves each selected capability against the effective registry, validates arguments and executes REASONING calls only through `CapabilityExecutor` under current authority.

Read results/errors and provider decisions are stored as bounded private working items for iterative continuation. Call identity, cancellation, budgets and restart handling are host-owned. Persisted pending work is not blindly replayed after restart.

Provider protocol handling permits bounded inert additive notifications while preserving strict identity/critical-event validation. Persisted terminal provider facts are sanitized rather than raw provider output.

## 3. Current effect lifecycle

Current effect path:

```text
one canonical PlanStepProposal
 -> prepare / preview / preconditions
 -> policy / approval
 -> revalidate
 -> durable write barrier
 -> execute under effective user
 -> verify
 -> verified receipt or recovery state
```

The write barrier commits immediately before the first possible effect. Business effect + completed plan data + verification/receipt share the business transaction. If that transaction is lost after the barrier, recovery semantics apply and the operation is not blindly retried.

### Current limitations

- Only one canonical plan/effect step is accepted; multi-step `EffectPlan` is future P6 work.
- After verified action execution, current product response still uses deterministic host completion prose rather than feeding the verified receipt back to the provider for natural post-effect synthesis. This is future P5 work.

## 4. Capability framework today

`CapabilityDefinition` is the atomic executable contract. Current decorator/registry metadata includes model-facing description/schema plus host-facing risk/effect/exposure/approval/configuration/groups/guards/budgets and optional preview/verification.

Current core providers:

```text
odoo_query
odoo_actions
odoo_batch
odoo_runtime
```

Settings can inspect the discovered catalog and enable/disable/configure current definitions.

Generic providers intentionally do not expose unrestricted ORM methods, SQL, Python, filesystem or shell.

This is a **current surface limitation, not a permanent product rule**. ADR-017/framework design allows explicit capabilities to wrap low-level services where authority is separately designed. Future Developer/Operator module/config/service/host operations require specialized definitions, technical profile and a privilege-boundary ADR.

Not implemented yet:

```text
external CapabilityProvider API
Skill/Bundle composition
ContextProvider
EvidenceProvider
EffectiveAssistantManifest
technical access profile
```

## 5. Conversation/context today

Complete messages/conversations are Odoo-persisted.

Provider input remains more limited than the target durable continuity model: current composition uses bounded recent conversation text plus screen/current-turn/capability context.

There is no current `ConversationContextManager` maintaining rolling structured summary, active entity/evidence references or explicit conversation-scoped preference state as a first-class context subsystem.

Screen context is only a bounded untrusted hint. Server code reconstructs identity/companies/permissions.

## 6. Queue and concurrency today

Backend turns are genuinely asynchronous/durable.

Current queue behavior includes:

- two `ir.cron` runner slots;
- lease token/expiry;
- bounded attempts;
- cancellation/stale recovery;
- `FOR UPDATE SKIP LOCKED` claim.

Therefore separate queued turns can be claimed by different slots without one SQL row lock serializing the whole queue.

However, **the current browser is still globally blocking at panel-state level**:

- `state.loading` prevents another submit;
- conversation selector is disabled while loading;
- model picker is disabled while loading;
- autonomy picker is disabled while loading;
- composer is disabled while loading.

So current backend concurrency does not yet provide a true multi-chat product experience.

Target P5 changes this to turn/conversation-scoped busy state, multiple conversations in parallel subject to configured capacity, and one active causal turn per conversation initially. Model/autonomy/profile changes while Turn A runs affect future turns only; A retains its captured execution snapshot.

Two cron slots are not the final capacity policy. Future concurrency is measured/configurable with provider/server capacity, fairness and backpressure.

## 7. Structured failures — Phase 2

P2 schema/provider/persistence/browser implementation exists.

P2.3 real Odoo validation passed at repaired checkpoint:

```text
8683ef6e3e8dd3820fe751f6e7726c9351fa7dfc
```

Recorded results include:

```text
addon update PASS
focused failure persistence 3 tests PASS
queue suite 9 tests PASS
full addon battery 95 tests / 0 failures/errors
HOOT 78 passed
unit tests 201 passed
repository tests 344 passed + 36 explicit skips
```

P2.4 browser failure presentation is implemented but Phase 2 is not formally complete until these hard real gates pass:

```text
P2-REAL-AUTH
P2-REAL-ACL
P2-REAL-TIMEOUT
P2-REAL-TOOLFAIL
P2-REAL-RECOVERY
```

## 8. Public activity — Phase 3 code landed, acceptance pending

Previous docs that say Phase 3 production has not started are stale.

Current `main` includes:

- closed bounded `PublicTurnEvent` projection;
- capability lifecycle -> trusted public activity mapping;
- independent `odoo.ai.turn.live.event` persistence;
- separate short cursor/transaction that does not commit worker business effects;
- live table/binding designed to avoid blocking pre-final visibility on the mutable turn;
- authenticated `/odoo_ai/v1/turn/live` endpoint;
- frontend live cursor consumption;
- current activity + expandable history UI;
- deterministic/Odoo/browser gate tooling.

Formal acceptance remains blocked by P2, then requires:

```text
P3-REAL-ACTIVITY-READ
P3-REAL-ACTIVITY-ACTION
P3-REAL-LIVE-VISIBILITY
P3-REAL-REDACTION
```

## 9. Answer streaming — Phase 4 code landed, acceptance pending

Current `main` includes `StreamingCodexDecisionEngine` and `StructuredFinalAnswerDeltaExtractor`.

It consumes Codex `item/agentMessage/delta`, extracts only the structured user-facing final-answer field and emits provisional answer text through the independent live channel.

Properties:

- provisional stream is non-authoritative;
- malformed provisional structure can disable streaming without weakening final validation;
- final strict `NextDecision` remains authority;
- activity and answer are distinct browser channels;
- browser uses Odoo-authenticated live polling/status reconciliation;
- polling vs SSE/bus is still a transport optimization choice.

Formal P4 acceptance requires P2 + P3 PASS, then:

```text
P4-REAL-FIRST-DELTA
P4-REAL-FINAL-PARITY
P4-REAL-CANCEL-STREAM
P4-REAL-UTF8-FRAGMENT
```

## 10. Retrieval/RAG today

No general current embedded RAG/Evidence provider exists yet.

The old sidecar Knowledge/Source implementation is historical only.

The current target in `KNOWLEDGE_INDEX.md` is broader than vector search:

```text
live Odoo/runtime/schema/configuration
source/XML intelligence
logs/diagnostics
company Knowledge/files
lexical FTS
semantic/vector only where evals justify it
web/external evidence later
```

Live business records remain live Odoo authority rather than stale indexed snapshots.

## 11. Technical operations today

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

These are target product capabilities in later gated phases, not rejected product goals.

Privileged host operations require a separate OS privilege-boundary ADR; high autonomy alone cannot grant them.

## 12. Imports/artifacts today

The current batch capability is bounded and suitable for small controlled collections, not a robust thousands-row intelligent import pipeline.

A future `DataImportSession` is planned for inspect/map/validate/correct/preview/chunk/receipt/resume semantics.

## 13. Formal roadmap state

```text
P0 COMPLETE
P1 COMPLETE
P2 REAL_ENV_VALIDATION_REQUIRED
P3 IMPLEMENTED_AWAITING_ORDERED_ACCEPTANCE
P4 IMPLEMENTED_AWAITING_ORDERED_ACCEPTANCE
P5+ NOT ELIGIBLE
```

Current hard order:

```text
P2 five PASS
 -> P3 four PASS
   -> P4 four PASS
     -> P5 READY
```

The P5+ roadmap is `research/AGENTIC_PRODUCT_EVOLUTION_PLAYBOOK.md`.

The P3/P4 landed code consumes the allowed look-ahead budget. Do not start another dependent product contract layer until the ordered acceptance chain is processed.

## 14. Next action

Run the current final `main` through the P2 gates using the real validation runbooks. If P2 passes, run P3; if P3 passes, run P4. Repair the smallest owning layer immediately on any hard-gate failure.

Only after P4 acceptance should implementation begin at P5.1 turn-scoped frontend/background state.
