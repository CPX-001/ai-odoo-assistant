# Stabilization execution state

State format: 8
Updated: 2026-08-28  
Accepted foundation runtime lineage through: `8a4432dc9852eacc422b8c794b6613c75da702a9`  
Accepted P5.1 implementation lineage through: `f7f924ce944db86e896745fef83ea2fb6fd6583a`
P5.1 validation harness lineage through: `c48534d3caec9b8a5301f840ca0f48c6aef4cacc`
P5.2a implementation lineage through: `5b952e4d47f0d59ed266df8b7803a88909bcfce0`
Roadmaps: `FOUNDATION_STABILIZATION_PLAYBOOK.md`, `E2E_AGENT_LOOP_CONVERGENCE.md`, `AGENTIC_PRODUCT_EVOLUTION_PLAYBOOK.md`

## Current cursor

```text
phase: 5
phase_name: natural non-blocking multi-chat product
phase_state: IN_PROGRESS
active_phase_record: docs/research/AGENTIC_PRODUCT_EVOLUTION_PLAYBOOK.md
active_slice: P5.2a-capacity-causal-eligibility
active_slice_record: docs/research/P5.2A_SCHEDULER_CAPACITY_CAUSALITY.md
active_slice_state: LOCAL_VALIDATION_REQUIRED
current_gate_type: CONTRACT_AND_DETERMINISTIC
blocking_validations: P5.2A-ODOO-SCHEDULER, P5.2A-TURN-QUEUE-REGRESSION
accepted_runtime_lineage: ba4ba00f9a913854a21b571cbb4559105347cca2 -> 8a4432dc9852eacc422b8c794b6613c75da702a9 -> f7f924ce944db86e896745fef83ea2fb6fd6583a
acceptance_evidence: docs/research/evidence/phase5/2026-08-28/P5.1-REAL-ACCEPTANCE-f7f924c.md
next_slice: NONE_UNTIL_P5.2A_DETERMINISTIC_VALIDATION
next_product_playbook: docs/research/AGENTIC_PRODUCT_EVOLUTION_PLAYBOOK.md
```

Phases 0 through 4 are complete. The ordered P2 -> P3 -> P4 real Odoo/browser/provider acceptance
chain passed on one linear code lineage. P5.1 production code and its deterministic, Odoo and real
browser/provider acceptance are complete. P5.2a scheduler capacity/causal-claim code is now landed,
but it is not accepted until its focused Odoo concurrency and queue-regression tests execute.

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

## P5.2a Capacity + causal eligibility — LOCAL_VALIDATION_REQUIRED

Implementation record:

```text
docs/research/P5.2A_SCHEDULER_CAPACITY_CAUSALITY.md
```

Landed implementation through `5b952e4d47f0d59ed266df8b7803a88909bcfce0` adds:

- a host-owned installation concurrency ceiling, currently bounded to the two physical cron slots;
- a short transaction-scoped PostgreSQL advisory lock around admission/claim only;
- race-safe global capacity counting before `queued -> running`;
- same-conversation causal predecessor eligibility based on turn creation identity rather than mutable `queued_at`;
- `awaiting_confirmation` as a causal blocker that does not consume worker capacity;
- administrator setting `Concurrent Assistant turns` with supported values 1..2;
- focused independent-cursor/thread tests for capacity and causal ordering.

No P5.2a test is recorded PASS from this connector-only implementation run. P5.2b must not consume
this scheduler claim contract until the focused Odoo tests and queue/failure regressions pass.

---

# Current known product limitations recorded for future phases

These limitations define the remaining Phase 5 and later work:

- background scopes are currently web-client memory; durable reconnect/continuity is expanded later in P5;
- P5.2a capacity/causal scheduler code is landed but unvalidated; fairness, anti-starvation and canonical capacity-release wake-up remain P5.2b;
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
- No GitHub Actions are used for roadmap validation under current instructions.

---

# Exact next action

Validate **P5.2a capacity + causal eligibility** before starting P5.2b:

```text
1. run focused TestAssistantTurnScheduler Odoo tests;
2. rerun existing turn queue and structured-failure suites;
3. run the full addon Odoo battery if focused tests pass;
4. repair the smallest owning P5.2a layer on any failure.
```

Only after deterministic/Odoo validation may execution implement P5.2b fairness, anti-starvation and
capacity-release wake-up. P5.2 real browser/provider acceptance remains P5.2c.