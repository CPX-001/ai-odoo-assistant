# Current implementation state

Foundation runtime acceptance was revalidated on 28 August 2026 through `8a4432dc9852eacc422b8c794b6613c75da702a9`. P5.1 turn-scoped frontend behavior is accepted through `f7f924ce944db86e896745fef83ea2fb6fd6583a`; its reproducible validation harness is `c48534d3caec9b8a5301f840ca0f48c6aef4cacc`. P5.2 scheduler concurrency/backpressure is accepted through `b4fbb034e113a41c26db77cb274f2b3b30f6eee3`. P5.3 stable settings snapshot is implemented through `1803826a6516e2703497f0d14d74850082ad7665` and accepted through the repaired validation/harness checkpoint `32e836e7789ea72f3ba0d32fe6bdabbb092f5953` after all four required gates passed.

This document distinguishes **implemented code** from **formal roadmap acceptance** and from the target in `PRODUCT_VISION.md`.

## 1. Product/deployment baseline

- Odoo 18 Community, self-hosted Linux.
- Addon: `addons/odoo_ai_assistant`, version `18.0.10.12.0` at the current manifest.
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

## 6. Queue, concurrency and per-turn settings today

Backend turns are genuinely asynchronous/durable.

P5.2 implementation now includes:

- two physical `ir.cron` runner slots;
- administrator-configurable logical concurrency ceiling, currently safely bounded to 1..2;
- short PostgreSQL advisory-lock coordination around admission/claim only;
- a `READ COMMITTED` scheduler claim transaction so lock waiters see prior committed claims instead of stale `REPEATABLE READ` snapshots;
- lease token/expiry and bounded attempts;
- cancellation/stale recovery and write-barrier recovery;
- one active causal turn per conversation based on durable predecessor identity rather than mutable queue timestamps;
- `awaiting_confirmation` as a same-conversation causal blocker that does not consume worker capacity;
- per-claim service watermark and cross-user anti-starvation ordering;
- retry/requeue fairness that does not regain priority solely from an older `queued_at`;
- scheduler wake-up after worker capacity is released/re-evaluated;
- post-commit wake-up when queued cancellation or approval/rejection releases a causal predecessor;
- bounded administrator-only diagnostics for capacity, active/queued/eligible/blocked counts and oldest queue wait.

Excess work remains durable `queued`; scheduler saturation is not a turn failure. `recovery_required` remains non-replayable and terminal for scheduler eligibility, so it does not permanently freeze a conversation.

This P5.2 behavior is implemented and accepted. Its deterministic Odoo tests, full addon regression,
HOOT/P5.1 regressions and three real browser/provider gates passed on the content lineage through
`b4fbb034e113a41c26db77cb274f2b3b30f6eee3`. See `research/P5.2_SCHEDULER_IMPLEMENTATION.md` and
`research/evidence/phase5/2026-08-29/P5.2-REAL-ACCEPTANCE-b4fbb03.md`.

### P5.3 stable settings snapshot implemented and accepted

Normal newly enqueued turns now derive a versioned `execution_settings_payload` from the already host-resolved persisted settings. Snapshot v1 contains:

```text
format_version
reasoning_model
autonomy_profile
policy
```

After capture, `reasoning_model`, `policy_payload` and `execution_settings_payload` are immutable for that turn. Later model/autonomy changes therefore apply to future turns, while approval/rejection may still resume the same persisted turn under its original captured settings.

The snapshot deliberately does not freeze revocable authorization or operational facts. User active state, company membership, ACL/record rules, capability guards/enablement and provider availability remain checked dynamically.

P5.3 is accepted. `P5.3-ODOO-SETTINGS-SNAPSHOT` passed with 2 tests,
`P5.3-DETERMINISTIC-REGRESSION` passed with 6 tests, the complete addon regression passed with 126
tests, and `P5-REAL-SETTINGS-SNAPSHOT` passed after review of the real browser observation. See
`research/P5.3_STABLE_SETTINGS_SNAPSHOT.md`, `research/P5.3_VALIDATION_RUNBOOK.md` and
`research/evidence/phase5/2026-08-29/P5.3-REAL-ACCEPTANCE-32e836e.md`.

### P5.1 frontend state implemented and accepted

The browser no longer relies solely on one panel-global execution owner. `zzz_assistant_turn_scope_service.js` introduces a per-conversation in-memory scope for:

```text
turn id/state
loading / decision loading
result / approval-recovery receipt
failure / error
streaming text
public activity
messages
```

The existing panel fields remain the projection of the currently visible scope so P2-P4 UI/contracts are reused rather than replaced.

Accepted current behavior is:

- Chat A can keep running while the user opens history or another/new conversation;
- Chat B can have its own loading/stream/activity/failure state;
- late A events do not intentionally overwrite visible B state;
- returning to A restores the in-memory scope;
- close/reopen does not intentionally cancel/restart the running server turn;
- model/autonomy controls are no longer disabled merely because the visible chat is running;
- conversation history can show compact runtime labels.

The full addon HOOT suite passed with 95 tests/370 assertions, the Odoo addon battery passed with
106 tests and no failures/errors, affected P2-P4 real regressions passed, and all three focused P5.1
browser gates passed. See `research/evidence/phase5/2026-08-28/P5.1-REAL-ACCEPTANCE-f7f924c.md`.

## 7. Structured failures — Phase 2 complete

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

P2.4 browser failure presentation passed its hard real gates on `ba4ba00`:

```text
P2-REAL-AUTH PASS
P2-REAL-ACL PASS
P2-REAL-TIMEOUT PASS
P2-REAL-TOOLFAIL PASS
P2-REAL-RECOVERY PASS
```

## 8. Public activity — Phase 3 complete

Previous docs that say Phase 3 production has not started are stale.

Current `main` includes:

- closed bounded `PublicTurnEvent` projection;
- capability lifecycle -> trusted public activity mapping;
- independent `odoo.ai.turn.live.event` persistence;
- separate short cursor/transaction that does not commit worker business effects;
- live row design that avoids an FK lock against the mutable turn;
- authenticated `/odoo_ai/v1/turn/live` endpoint;
- frontend live cursor consumption;
- current activity + expandable history UI;
- deterministic/Odoo/browser gate tooling.

```text
P3-REAL-ACTIVITY-READ PASS
P3-REAL-ACTIVITY-ACTION PASS
P3-REAL-LIVE-VISIBILITY PASS
P3-REAL-REDACTION PASS
```

## 9. Answer streaming — Phase 4 complete

Current `main` includes `StreamingCodexDecisionEngine` and `StructuredFinalAnswerDeltaExtractor`.

It consumes Codex `item/agentMessage/delta`, extracts only the structured user-facing final-answer field and emits provisional answer text through the independent live channel.

Properties:

- provisional stream is non-authoritative;
- malformed provisional structure can disable streaming without weakening final validation;
- final strict `NextDecision` remains authority;
- activity and answer are distinct browser channels;
- browser uses Odoo-authenticated live polling/status reconciliation;
- polling vs SSE/bus is still a transport optimization choice.

```text
P4-REAL-FIRST-DELTA PASS
P4-REAL-FINAL-PARITY PASS
P4-REAL-CANCEL-STREAM PASS
P4-REAL-UTF8-FRAGMENT PASS
```

The combined sanitized acceptance record is
`research/evidence/phase4/2026-08-28/P2-P4-REAL-ACCEPTANCE.md`.

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
P2 COMPLETE
P3 COMPLETE
P4 COMPLETE
P5 IN_PROGRESS — P5.1, P5.2 and P5.3 COMPLETE; P5.4 READY
P6+ NOT ELIGIBLE
```

Current accepted foundation order:

```text
P2 five PASS
 -> P3 four PASS
   -> P4 four PASS
   -> P5.1 accepted
     -> P5.2 accepted
```

The P5+ roadmap is `research/AGENTIC_PRODUCT_EVOLUTION_PLAYBOOK.md`. P5.2 acceptance is recorded in
`research/evidence/phase5/2026-08-29/P5.2-REAL-ACCEPTANCE-b4fbb03.md`. P5.3 implementation is recorded
in `research/P5.3_STABLE_SETTINGS_SNAPSHOT.md`; all focused, deterministic, full-addon and real
browser gates are accepted in `research/evidence/phase5/2026-08-29/P5.3-REAL-ACCEPTANCE-32e836e.md`.

## 14. Next action

Define P5.4 final activity/answer/failure UX as one bounded slice from
`research/AGENTIC_PRODUCT_EVOLUTION_PLAYBOOK.md`, with explicit deterministic and real acceptance
gates. P5.4 is ready but not implemented.
