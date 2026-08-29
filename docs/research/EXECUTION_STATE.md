# Stabilization execution state

State format: 12
Updated: 2026-08-29
Accepted foundation runtime lineage through: `8a4432dc9852eacc422b8c794b6613c75da702a9`  
Accepted P5.1 implementation lineage through: `f7f924ce944db86e896745fef83ea2fb6fd6583a`
P5.1 validation harness lineage through: `c48534d3caec9b8a5301f840ca0f48c6aef4cacc`
P5.2 implementation/harness lineage through: `b1e49d97fce5506a2c9bb19b3a9ce1303f7add9c`
Accepted P5.2 validation/harness lineage through: `b4fbb034e113a41c26db77cb274f2b3b30f6eee3`
P5.3 implementation/harness lineage through: `1803826a6516e2703497f0d14d74850082ad7665`
P5.3 focused Odoo validation lineage through: `b7428d7804cdbea263ea78ad5b588398b02fe5be`
Roadmaps: `FOUNDATION_STABILIZATION_PLAYBOOK.md`, `E2E_AGENT_LOOP_CONVERGENCE.md`, `AGENTIC_PRODUCT_EVOLUTION_PLAYBOOK.md`

## Current cursor

```text
phase: 5
phase_name: natural non-blocking multi-chat product
phase_state: IN_PROGRESS
active_phase_record: docs/research/AGENTIC_PRODUCT_EVOLUTION_PLAYBOOK.md
active_slice: P5.3-stable-settings-snapshot
active_slice_record: docs/research/P5.3_STABLE_SETTINGS_SNAPSHOT.md
active_slice_state: LOCAL_VALIDATION_REQUIRED
current_gate_type: HARD_DETERMINISTIC_REGRESSION
blocking_validations: P5.3-DETERMINISTIC-REGRESSION, P5-REAL-SETTINGS-SNAPSHOT
accepted_runtime_lineage: ba4ba00f9a913854a21b571cbb4559105347cca2 -> 8a4432dc9852eacc422b8c794b6613c75da702a9 -> f7f924ce944db86e896745fef83ea2fb6fd6583a -> b4fbb034e113a41c26db77cb274f2b3b30f6eee3
acceptance_evidence: docs/research/evidence/phase5/2026-08-29/P5.2-REAL-ACCEPTANCE-b4fbb03.md
latest_validation_evidence: docs/research/evidence/phase5/2026-08-29/P5.3-FOCUSED-ODOO-b7428d7.md
next_slice: P5.3-deterministic-regression
next_product_playbook: docs/research/AGENTIC_PRODUCT_EVOLUTION_PLAYBOOK.md
```

Phases 0 through 4 are complete. The ordered P2 -> P3 -> P4 real Odoo/browser/provider acceptance
chain passed on one linear code lineage. P5.1 production code and its deterministic, Odoo and real
browser/provider acceptance are complete. P5.2 scheduler capacity, causal ordering, fairness,
release wake-up, diagnostics and real two-cron behavior are accepted. P5.3 is implemented in small
contract/test/version slices and its focused Odoo snapshot gate passed. Its bounded deterministic
regression and formal real product-path gate remain pending.

---

# Phase 0 — COMPLETE

Reproducible baseline and timing/failure evidence are complete according to `PHASE0_BASELINE.md`.

# Phase 1 — COMPLETE

Provider boundary / host-owned iterative decision loop is complete.

Retained real evidence:

```text
P1-REAL-VERSION  | PASS | 49bdac1f732acaaee3154ed60baffd675130991a | Codex 0.149.1
P1-REAL-SOAK-100 | PASS | 49bdac1f732acaaee3154ed60baffd675130991a | 100/100 turns
P1-REAL-TOOLCALL | PASS | db6e5c12c53e9a99ad3a55f7472eb13f93855a06
P1-REAL-CANCEL   | PASS | db6e5c12c53e9a99ad3a55f7472eb13f93855a06
```

ADR-019/current code own the active host loop.

---

# Phase 2 — COMPLETE

## P2.1 FailureEnvelope — COMPLETE

Bounded host contract:

```text
code
category
stage
component
retryability
effect_state
user_action
safe_summary
safe_details
diagnostic_id
provider_code
```

## P2.2 Provider normalization — COMPLETE

Sanitized provider category/status/upstream facts survive without raw provider output becoming product state.

## P2.3 Terminal persistence — COMPLETE and real validated

Material repaired checkpoint:

```text
8683ef6e3e8dd3820fe751f6e7726c9351fa7dfc
```

Recorded validation:

```text
addon install/update                PASS
focused failure persistence          3 tests / 0 failed
turn queue suite                      9 tests / 0 failed
full addon battery                    95 tests / 0 failed/errors
HOOT @odoo_ai_assistant               78 passed
unit tests                            201 passed
repository tests                      344 passed + 36 explicit skips
```

Evidence:

```text
docs/research/evidence/phase2/2026-08-28/P2.3-ODOO-VALIDATION-8683ef6.md
```

## P2.4 Browser failure presentation — COMPLETE

```text
P2-REAL-AUTH      | HARD | PASS | ba4ba00
P2-REAL-ACL       | HARD | PASS | ba4ba00
P2-REAL-TIMEOUT   | HARD | PASS | ba4ba00
P2-REAL-TOOLFAIL  | HARD | PASS | ba4ba00
P2-REAL-RECOVERY  | HARD | PASS | ba4ba00
```

The browser presentation/effect semantics were observed on the supported real product path. See
`evidence/phase4/2026-08-28/P2-P4-REAL-ACCEPTANCE.md`.

---

# Phase 3 — COMPLETE

Previous documents described Phase 3 as preparation-only. That is stale.

Current runtime now contains:

- production closed `PublicTurnEvent` projection;
- trusted capability lifecycle -> public activity mapping;
- independent `odoo.ai.turn.live.event` persistence;
- separate short cursor/transaction that does not commit the worker business transaction;
- live row design that avoids an FK lock against the mutable worker turn;
- authenticated `/odoo_ai/v1/turn/live` route;
- browser live cursor consumer;
- public activity panel/history;
- focused Odoo/deterministic/browser gate tooling.

Important invariant: public live persistence never authorizes a capability or commits business effects merely to make UX progress visible.

```text
P3-REAL-ACTIVITY-READ    | HARD | PASS | ba4ba00
P3-REAL-ACTIVITY-ACTION  | HARD | PASS | ba4ba00
P3-REAL-LIVE-VISIBILITY  | HARD | PASS | ba4ba00
P3-REAL-REDACTION        | HARD | PASS | ba4ba00
```

---

# Phase 4 — COMPLETE

Current runtime contains:

- `StructuredFinalAnswerDeltaExtractor`;
- `StreamingCodexDecisionEngine` installed at the existing provider seam;
- Codex `item/agentMessage/delta` handling;
- provisional `answer.delta` live persistence;
- separate browser `activity` and `answer` channels;
- final authoritative response reconciliation;
- P4 browser gate tooling/runbook.

Provisional answer text is non-authoritative. The final validated `NextDecision` remains authority and streaming cannot authorize an effect.

```text
P4-REAL-FIRST-DELTA      | HARD | PASS | 8a4432d
P4-REAL-FINAL-PARITY     | HARD | PASS | 8a4432d
P4-REAL-CANCEL-STREAM    | HARD | PASS | 8a4432d
P4-REAL-UTF8-FRAGMENT    | HARD | PASS | 8a4432d
```

The cancellation gate was rerun with all P4 gates after its bounded-fixture repair.

---

# Phase 5 — IN_PROGRESS

The product direction is documented in:

```text
docs/PRODUCT_VISION.md
docs/research/AGENTIC_PRODUCT_EVOLUTION_PLAYBOOK.md
```

It adds gated phases for:

```text
P5  natural non-blocking multi-chat + post-effect synthesis + continuity
P6  TaskPlan / multi-step EffectPlan / budgets / EffectJournal
P7  mini-framework / self-awareness / progressive capability discovery
P8  Evidence / source / runtime / logs
P9  company Knowledge / RAG
P10 Developer/Operator host operations
P11 advanced imports/artifacts
P12 controlled source writes
P13 multimodal + web evidence
P14 additional surfaces/automation/MCP
P15 additional providers
```

## P5.1 Turn-scoped frontend/background state — COMPLETE

Implementation record:

```text
docs/research/P5.1_TURN_SCOPED_FRONTEND_STATE.md
```

Current implementation introduces per-conversation in-memory execution scopes while retaining the
existing P2-P4 panel fields as the projection of the currently visible scope. This allows background
Chat A state to continue without owning Chat B's loading/activity/answer/failure fields.

Landed behavior includes:

- temporary `new:N` scope -> durable `conversation:<uuid>` binding after enqueue;
- per-conversation `turnId`, turn state, loading, approval/recovery, failure, activity and answer state;
- late background callbacks update only their owning scope;
- history/new-chat navigation no longer depends on another chat's running state;
- model/autonomy controls remain selectable while another turn runs;
- compact conversation runtime labels;
- close/reopen keeps the web-client scope and does not intentionally cancel/restart server work;
- focused HOOT contract tests are present.

Accepted validation:

```text
P5.1-HOOT-TURN-SCOPES           | PASS | 95 tests / 370 assertions
P5.1-P2-P4-REGRESSION           | PASS | P2 five, P3 representative two, P4 representative two
P5.1-BROWSER-MULTICHAT          | PASS
P5.1-BROWSER-SETTINGS-SNAPSHOT  | PASS
P5.1-BROWSER-REOPEN             | PASS
```

Evidence: `evidence/phase5/2026-08-28/P5.1-REAL-ACCEPTANCE-f7f924c.md`.

## P5.2 Scheduler concurrency/backpressure — COMPLETE

Implementation records:

```text
docs/research/P5.2A_SCHEDULER_CAPACITY_CAUSALITY.md
docs/research/P5.2_SCHEDULER_IMPLEMENTATION.md
docs/research/P5.2_VALIDATION_RUNBOOK.md
```

Implemented P5.2 behavior now includes:

- installation-wide capacity bounded to the current two physical cron slots;
- race-safe claim admission with a short PostgreSQL advisory lock;
- scheduler claim cursor using `READ COMMITTED` so lock waiters observe previously committed claims;
- same-conversation causal serialization based on durable turn identity;
- `awaiting_confirmation` as a causal blocker without consuming worker capacity;
- per-claim `scheduler_claimed_at` service watermark;
- fairness order: fewer active turns -> least recently served user -> FIFO;
- retry/requeue cannot regain priority solely from an older queue timestamp;
- wake-up after a claimed worker releases/re-evaluates capacity;
- post-commit wake-up for queued cancellation and approval/rejection causal release;
- bounded administrator-only scheduler diagnostics;
- focused fairness/wake-up Odoo tests and P5.2 real browser gate tooling.

Accepted validation:

```text
P5.2-FOCUSED-ODOO              | PASS | 29 tests, 0 failures/errors
P5.2-FULL-ADDON-REGRESSION     | PASS | 123 tests, 0 failures/errors
P5.2-HOOT-REGRESSION           | PASS | 95 tests / 370 assertions
P5.1-BROWSER-MULTICHAT         | PASS
P5.1-BROWSER-REOPEN            | PASS
P5-REAL-MULTICHAT              | PASS | peak active 2 at capacity 2
P5-REAL-CONVERSATION-ORDERING  | PASS | successor queued, then running after release
P5-REAL-BACKPRESSURE           | PASS | no over-admission at capacity 1; wake 1,674 ms
```

Evidence: `evidence/phase5/2026-08-29/P5.2-REAL-ACCEPTANCE-b4fbb03.md`.

## P5.3 Stable settings snapshot — LOCAL_VALIDATION_REQUIRED

Implementation/validation records:

```text
docs/research/P5.3_STABLE_SETTINGS_SNAPSHOT.md
docs/research/P5.3_VALIDATION_RUNBOOK.md
```

Implemented in deliberately small checkpoints:

```text
P5.3a versioned immutable settings snapshot | b46b72e
P5.3b focused Odoo test harness              | 186eed0
P5.3c addon version checkpoint               | 1803826
```

New normal turns derive a host-owned `execution_settings_payload` from the already resolved
`reasoning_model` and `policy_payload`. The v1 snapshot records model, autonomy profile and policy;
after capture those three persisted settings surfaces cannot be rewritten on that turn. Dynamic
Odoo authorization, company membership, capability guards and provider availability remain live
checks and are not frozen by the snapshot.

The P5.1 real browser evidence already demonstrated that A retained persisted model/policy while B
captured changed preferences. That older evidence is supporting context only; it does not accept the
new P5.3 contract or SHA.

Executed focused validation:

```text
P5.3-ODOO-SETTINGS-SNAPSHOT | HARD | PASS | 2 tests, 0 failures/errors | b7428d7
```

Evidence: `evidence/phase5/2026-08-29/P5.3-FOCUSED-ODOO-b7428d7.md`.

No repair was required. P5.3 validation now continues as a separate bounded deterministic regression
slice, followed by the formal `P5-REAL-SETTINGS-SNAPSHOT` gate. P5.4 remains blocked until all P5.3
acceptance gates pass.

---

# Current known product limitations recorded for future phases

These limitations define the remaining Phase 5 and later work:

- background scopes are currently web-client memory; durable reconnect/continuity is expanded later in P5;
- P5.3 stable settings snapshot passed its focused Odoo gate but still awaits bounded regression and formal real product-path validation; P5.4 is blocked;
- post-effect verified actions still need provider continuation/natural synthesis (P5.5);
- conversation provider context is smaller than the target durable `ConversationContextManager` model (P5.6);
- one canonical effect proposal/step is supported; multi-step effects are P6;
- no external `CapabilityProvider`/Skill/ContextProvider/EvidenceProvider contract exists yet;
- no general Evidence/RAG/source/log provider exists in the active embedded capability package;
- no Developer/Operator privileged host-operation boundary exists;
- no staged large-import workflow exists.

---

# Invariants carried forward

- Odoo remains persistence/operational authority.
- Business capabilities execute under effective user with `su=False`.
- `CapabilityDefinition` remains atomic executable authority.
- Provider facts are advisory/bounded; host owns effect certainty.
- Durable write barrier and recovery semantics remain authoritative.
- Raw provider output/private reasoning is not public activity.
- No parallel tool authority registry is introduced.
- P5 target concurrency is per-turn/per-conversation, not a global UI lock.
- Model/autonomy/profile changes after a turn is queued do not mutate that running turn's captured authority/settings.
- P5.3 freezes execution selectors, not revocable Odoo authorization or dynamic capability guards.
- No GitHub Actions are used for roadmap validation under current instructions.

---

# Exact next action

Run the separate bounded deterministic P5.3 regression slice from `P5.3_VALIDATION_RUNBOOK.md` against
the exact current lineage. Cover turn enqueue/idempotency, user model/autonomy preferences, policy
resolution, approval same-turn requeue/resume, and embedded-runtime consumption of persisted
`reasoning_model`/`policy_payload`. If it fails, repair only the smallest responsible layer and rerun
the affected coverage. Do not start P5.4 or the formal real product-path gate until this regression
slice passes.
