# Stabilization execution state

State format: 4  
Updated: 2026-08-28  
Runtime implementation baseline audited for this reconciliation: `24b9460ad09998ec50d853e0a715b543e5991bbb`  
Roadmaps: `FOUNDATION_STABILIZATION_PLAYBOOK.md`, `E2E_AGENT_LOOP_CONVERGENCE.md`, `AGENTIC_PRODUCT_EVOLUTION_PLAYBOOK.md`

## Current cursor

```text
phase: 2
phase_name: structured failure contract
phase_state: IN_PROGRESS
active_phase_record: docs/research/PHASE2_FAILURE_CONTRACT.md
active_slice: P2.4-browser-failure-presentation
active_slice_record: docs/research/P2.4_BROWSER_FAILURE_PRESENTATION.md
active_slice_state: REAL_ENV_VALIDATION_REQUIRED
current_gate_type: HARD_REAL_ENV
blocking_validations: P2-REAL-AUTH, P2-REAL-ACL, P2-REAL-TIMEOUT, P2-REAL-TOOLFAIL, P2-REAL-RECOVERY
phase_completion_validations: P2-REAL-AUTH, P2-REAL-ACL, P2-REAL-TIMEOUT, P2-REAL-TOOLFAIL, P2-REAL-RECOVERY
next_slice: NONE_UNTIL_PHASE2_REAL_GATES_PASS
lookahead_budget: EXHAUSTED_BY_LANDED_P3_P4_CONTRACTS
next_product_phase_after_p4_acceptance: 5
next_product_playbook: docs/research/AGENTIC_PRODUCT_EVOLUTION_PLAYBOOK.md
```

Phase 0 and Phase 1 are complete. Phase 2 implementation is complete through the browser failure consumer but its five real presentation gates remain mandatory.

Unlike the previous state document, current `main` **does contain production implementation for Phase 3 public activity and Phase 4 provisional answer streaming**. Those layers were landed as bounded look-ahead so one real Odoo/browser/provider session can validate the ordered chain. Their existence does not make them formally complete.

No additional P5+ contract implementation is eligible until the P2 -> P3 -> P4 real acceptance chain is processed.

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

# Phase 2 — IN_PROGRESS / hard real gates pending

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

## P2.4 Browser failure presentation — REAL_ENV_VALIDATION_REQUIRED

Implementation exists and deterministic preparation was recorded. Formal Phase 2 completion still requires:

```text
P2-REAL-AUTH      | HARD | NOT RUN/PENDING
P2-REAL-ACL       | HARD | NOT RUN/PENDING
P2-REAL-TIMEOUT   | HARD | NOT RUN/PENDING
P2-REAL-TOOLFAIL  | HARD | NOT RUN/PENDING
P2-REAL-RECOVERY  | HARD | NOT RUN/PENDING
```

Backend fixture success alone is insufficient; browser presentation/effect semantics must be observed on the real supported path.

---

# Phase 3 — IMPLEMENTED_AWAITING_ORDERED_ACCEPTANCE

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

Formal acceptance is blocked until all P2 real gates pass.

Then execute:

```text
P3-REAL-ACTIVITY-READ    | HARD | BLOCKED_BY_P2
P3-REAL-ACTIVITY-ACTION  | HARD | BLOCKED_BY_P2
P3-REAL-LIVE-VISIBILITY  | HARD | BLOCKED_BY_P2
P3-REAL-REDACTION        | HARD | BLOCKED_BY_P2
```

A failure repairs Phase 3 before Phase 4 acceptance may count.

---

# Phase 4 — IMPLEMENTED_AWAITING_ORDERED_ACCEPTANCE

Current runtime contains:

- `StructuredFinalAnswerDeltaExtractor`;
- `StreamingCodexDecisionEngine` installed at the existing provider seam;
- Codex `item/agentMessage/delta` handling;
- provisional `answer.delta` live persistence;
- separate browser `activity` and `answer` channels;
- final authoritative response reconciliation;
- P4 browser gate tooling/runbook.

Provisional answer text is non-authoritative. The final validated `NextDecision` remains authority and streaming cannot authorize an effect.

Formal acceptance is blocked until P2 and all P3 gates pass.

Then execute:

```text
P4-REAL-FIRST-DELTA      | HARD | BLOCKED_BY_P2_P3
P4-REAL-FINAL-PARITY     | HARD | BLOCKED_BY_P2_P3
P4-REAL-CANCEL-STREAM    | HARD | BLOCKED_BY_P2_P3
P4-REAL-UTF8-FRAGMENT    | HARD | BLOCKED_BY_P2_P3
```

Use `PHASE34_REAL_VALIDATION_RUNBOOK.md`.

---

# P5+ product roadmap — NOT ELIGIBLE

The new product direction is documented in:

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

These are product plans, not current implementation claims.

---

# Current known product limitations recorded for future phases

These are not reasons to bypass the active P2-P4 hard gate, but are now explicitly captured so later work does not discover them accidentally:

- frontend uses panel-global `state.loading` and currently disables composer/conversation/model/autonomy controls while a visible turn runs;
- backend currently has two cron slots rather than a measured/configurable concurrency policy;
- one canonical effect proposal/step is supported;
- verified action execution currently ends with deterministic host completion prose rather than provider post-effect synthesis;
- conversation provider context is smaller than the target durable continuity model;
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

On a disposable real Odoo 18 environment, test the **current final `main` SHA** using the existing runbooks.

First run all Phase 2 gates:

```text
P2-REAL-AUTH
P2-REAL-ACL
P2-REAL-TIMEOUT
P2-REAL-TOOLFAIL
P2-REAL-RECOVERY
```

If any fails: record evidence, create the smallest P2 repair slice, add deterministic regression coverage and rerun that gate. Do not count P3/P4 acceptance.

If all P2 gates pass: formally close Phase 2, then execute all four P3 gates on the same accepted code lineage.

If all P3 gates pass: formally close Phase 3, then execute all four P4 gates.

If all P4 gates pass: update this cursor to Phase 5 `READY` and select **P5.1 turn-scoped frontend/background state** from `AGENTIC_PRODUCT_EVOLUTION_PLAYBOOK.md`.
