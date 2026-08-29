# Stabilization execution state

State format: 20  
Updated: 2026-08-29

Accepted foundation/runtime lineage:

```text
P0-P4 through 8a4432dc9852eacc422b8c794b6613c75da702a9
P5.1 accepted through f7f924ce944db86e896745fef83ea2fb6fd6583a
P5.2 accepted through b4fbb034e113a41c26db77cb274f2b3b30f6eee3
P5.3 accepted through 32e836e7789ea72f3ba0d32fe6bdabbb092f5953
P5.4 accepted through 3e2b38d68fe172cd2cf92d7794159f73476ac23d
P5.5 accepted through 8427c8849b1e1f3afa6337de1209a6027410c266
```

Current unaccepted P5.6 lineage:

```text
implementation: f141f1dd56b95c5eb3e372bc61a49f265772c657
validation batch/harness: 29452d85e2c21f625fc38b5bda814524168be5f2
implementation record: docs/research/P5.6_CONVERSATION_CONTEXT_MANAGER.md
validation runbook: docs/research/P5.6_VALIDATION_RUNBOOK.md
acceptance batch: tests/e2e/p5_6_acceptance_batch.py
```

Roadmaps:

```text
docs/research/FOUNDATION_STABILIZATION_PLAYBOOK.md
docs/research/E2E_AGENT_LOOP_CONVERGENCE.md
docs/research/AGENTIC_PRODUCT_EVOLUTION_PLAYBOOK.md
```

## Current cursor

```text
phase: 5
phase_name: natural non-blocking multi-chat product
phase_state: IN_PROGRESS
active_phase_record: docs/research/AGENTIC_PRODUCT_EVOLUTION_PLAYBOOK.md
active_slice: P5.6-conversation-context-manager
active_slice_record: docs/research/P5.6_CONVERSATION_CONTEXT_MANAGER.md
active_slice_state: LOCAL_VALIDATION_REQUIRED
current_gate_type: HARD_LOCAL_AND_REAL
blocking_validations: P5.6-ODOO-CONTEXT, P5.6-DETERMINISTIC-REGRESSION, P5.6-FULL-ADDON-REGRESSION, P5-REAL-CONTINUITY
accepted_runtime_lineage: ba4ba00f9a913854a21b571cbb4559105347cca2 -> 8a4432dc9852eacc422b8c794b6613c75da702a9 -> f7f924ce944db86e896745fef83ea2fb6fd6583a -> b4fbb034e113a41c26db77cb274f2b3b30f6eee3 -> 32e836e7789ea72f3ba0d32fe6bdabbb092f5953 -> 3e2b38d68fe172cd2cf92d7794159f73476ac23d -> 8427c8849b1e1f3afa6337de1209a6027410c266
latest_accepted_evidence: docs/research/evidence/phase5/2026-08-29/P5.5-REAL-ACCEPTANCE-8427c88.md
next_action: execute the complete P5.6 acceptance batch and review the bounded real observation
blocked_successor: P5.7-conversation-scoped-preferences
next_product_playbook: docs/research/AGENTIC_PRODUCT_EVOLUTION_PLAYBOOK.md
```

P5.6 is one coherent implementation slice. The next boundary is validation, not another product micro-slice.

---

# Phase 0 — COMPLETE

Reproducible baseline and timing/failure evidence are complete according to `PHASE0_BASELINE.md`.

# Phase 1 — COMPLETE

Provider boundary and host-owned iterative decision loop are accepted. Retained real evidence includes:

```text
P1-REAL-VERSION  PASS
P1-REAL-SOAK-100 PASS
P1-REAL-TOOLCALL PASS
P1-REAL-CANCEL   PASS
```

ADR-019/current code owns active orchestration.

# Phase 2 — COMPLETE

Structured failure normalization, provider facts, terminal persistence and browser presentation are accepted.

Representative accepted real gates:

```text
P2-REAL-AUTH      PASS
P2-REAL-ACL       PASS
P2-REAL-TIMEOUT   PASS
P2-REAL-TOOLFAIL  PASS
P2-REAL-RECOVERY  PASS
```

# Phase 3 — COMPLETE

Public activity uses bounded host-owned projections and independent live persistence. Raw provider/private reasoning is not public activity.

```text
P3-REAL-ACTIVITY-READ    PASS
P3-REAL-ACTIVITY-ACTION  PASS
P3-REAL-LIVE-VISIBILITY  PASS
P3-REAL-REDACTION        PASS
```

# Phase 4 — COMPLETE

Structured provisional answer streaming is accepted while final validated `NextDecision` remains authority.

```text
P4-REAL-FIRST-DELTA    PASS
P4-REAL-FINAL-PARITY   PASS
P4-REAL-CANCEL-STREAM  PASS
P4-REAL-UTF8-FRAGMENT  PASS
```

# Phase 5 — IN_PROGRESS

Product direction: `AGENTIC_PRODUCT_EVOLUTION_PLAYBOOK.md`.

## P5.1 Turn-scoped frontend/background state — COMPLETE

Accepted behavior includes independent conversation scopes, non-blocking navigation/new chat, close/reopen without restart and model/autonomy controls not globally locked by another running turn.

Evidence: `evidence/phase5/2026-08-28/P5.1-REAL-ACCEPTANCE-f7f924c.md`.

## P5.2 Scheduler concurrency/backpressure — COMPLETE

Accepted implementation includes bounded two-slot scheduling, same-conversation causality, cross-conversation concurrency, fairness, queue backpressure, wake-up and diagnostics.

```text
P5-REAL-MULTICHAT              PASS
P5-REAL-CONVERSATION-ORDERING PASS
P5-REAL-BACKPRESSURE           PASS
```

Evidence: `evidence/phase5/2026-08-29/P5.2-REAL-ACCEPTANCE-b4fbb03.md`.

## P5.3 Stable settings snapshot — COMPLETE

Per-turn model/policy/autonomy selectors are versioned and immutable for that turn; revocable ACL/capability/provider facts remain dynamic.

```text
P5.3-ODOO-SETTINGS-SNAPSHOT    PASS
P5.3-DETERMINISTIC-REGRESSION  PASS
P5.3-FULL-ADDON-REGRESSION     PASS
P5-REAL-SETTINGS-SNAPSHOT      PASS
```

Evidence: `evidence/phase5/2026-08-29/P5.3-REAL-ACCEPTANCE-32e836e.md`.

## P5.4 Final activity/answer/failure UX — COMPLETE

One authoritative final Assistant message per turn, public activity separated from prose, explicit approval/failure/recovery, and no fake thinking bubble when real activity exists.

```text
P5-REAL-CHAT-BASIC    PASS
P5-REAL-ERROR-UX      PASS
P5-REAL-APPROVAL-UX   PASS
P5-REAL-RECOVERY-UX   PASS
```

Evidence: `evidence/phase5/2026-08-29/P5.4-REAL-ACCEPTANCE-3e2b38d.md`.

## P5.5 Post-effect reasoning — COMPLETE

Verified effect receipt is appended before provider continuation. Post-effect reasoning receives no PLAN catalog and cannot repeat the completed effect.

```text
P5.5-ODOO-POST-EFFECT          PASS
P5.5-DETERMINISTIC-REGRESSION PASS
P5.5-FULL-ADDON-REGRESSION    PASS
P5-REAL-POST-EFFECT            PASS
```

Evidence: `evidence/phase5/2026-08-29/P5.5-REAL-ACCEPTANCE-8427c88.md`.

## P5.6 ConversationContextManager — LOCAL_VALIDATION_REQUIRED

Implementation is present on `main` and deliberately covers the whole P5.6 context contract in one slice:

```text
versioned immutable per-turn conversation context checkpoint
recent raw messages ordered by causal predecessor turns
bounded rolling structured summary
active Odoo model/record references
relevant verified-effect references
reserved bounded evidence references
bounded session settings with captured Odoo-language fallback
provider-seam serialization <= 8,000 chars
```

Full Odoo messages/turns remain history authority. Context is derived data and never grants authorization.

The implementation fixes the Phase-5 ordering hazard where Turn B can be queued before Turn A's Assistant reply is persisted: provider context is now constructed from predecessor turn identity/order, not raw message creation order. Current and future same-conversation turns are excluded.

Prepared validation is intentionally grouped:

```text
P5.6-ODOO-CONTEXT
  -> P5.6-DETERMINISTIC-REGRESSION
  -> P5.6-FULL-ADDON-REGRESSION
  -> P5-REAL-CONTINUITY
  -> bounded evidence review
```

No P5.6 PASS is claimed yet because this GitHub-only implementation run cannot execute the disposable Odoo/Codex/Chromium environment.

---

# Current known limitations after P5.6 implementation

- P5.6 has not yet crossed its executable acceptance boundary.
- Conversation-scoped preference mutations are P5.7; P5.6 only carries the bounded session-settings slot/fallback.
- One canonical effect step remains the P5 limit; multi-step effects are P6.
- No external `CapabilityProvider` / Skill / ContextProvider / EvidenceProvider contract yet; those are later phases.
- No general embedded RAG/Evidence provider yet.
- No privileged Developer/Operator host-operation boundary yet.
- No staged large-import workflow yet.

---

# Invariants carried forward

- Odoo remains persistence and operational authority.
- Business capabilities run under the effective user with `su=False`.
- `CapabilityDefinition` remains atomic executable authority.
- Provider facts/context are advisory bounded data; host owns effect certainty.
- Durable write barrier and recovery semantics remain authoritative.
- Raw provider output/private reasoning is never public activity.
- No parallel tool-authority registry is introduced.
- One active causal turn per conversation; independent conversations may run concurrently within scheduler capacity.
- Turn settings snapshots are immutable but revocable Odoo authorization stays dynamic.
- P5.5 post-effect continuation has no PLAN authority.
- P5.6 context snapshots are derived from Odoo history and cannot authorize tools/effects.
- No GitHub Actions are used for roadmap validation under current instructions.

---

# Exact next action

Run the complete prepared P5.6 batch on a clean checkout of current `main`:

```bash
python tests/e2e/p5_6_acceptance_batch.py \
  --summary-out /tmp/p5_6_acceptance.json
```

Do **not** stop manually after a green focused gate. Continue through deterministic, full-addon and real continuity checks unless a genuine failure blocks the chain. If all executable gates succeed, review the sanitized observation, record exact-SHA evidence, mark P5.6 `COMPLETE`, and continue directly into P5.7.
