# Stabilization execution state

State format: 24
Updated: 2026-08-29

Accepted foundation/runtime lineage:

```text
P0-P4 through 8a4432dc9852eacc422b8c794b6613c75da702a9
P5.1 accepted through f7f924ce944db86e896745fef83ea2fb6fd6583a
P5.2 accepted through b4fbb034e113a41c26db77cb274f2b3b30f6eee3
P5.3 accepted through 32e836e7789ea72f3ba0d32fe6bdabbb092f5953
P5.4 accepted through 3e2b38d68fe172cd2cf92d7794159f73476ac23d
P5.5 accepted through 8427c8849b1e1f3afa6337de1209a6027410c266
P5.6 accepted through 720102f2a13af5240c779b07cc71ee65994a87b1
P5.7 model/reasoning preference sub-slice accepted through eb66e45447c4d64e1ebbb5e8322bffa759c12773
```

Accepted P5.6 lineage:

```text
implementation: f141f1dd56b95c5eb3e372bc61a49f265772c657
validation batch/harness: 29452d85e2c21f625fc38b5bda814524168be5f2
validation repairs and accepted checkpoint: 720102f2a13af5240c779b07cc71ee65994a87b1
implementation record: docs/research/P5.6_CONVERSATION_CONTEXT_MANAGER.md
validation runbook: docs/research/P5.6_VALIDATION_RUNBOOK.md
acceptance batch: tests/e2e/p5_6_acceptance_batch.py
```

Roadmaps:

```text
docs/research/FOUNDATION_STABILIZATION_PLAYBOOK.md
docs/research/E2E_AGENT_LOOP_CONVERGENCE.md
docs/research/AGENTIC_PRODUCT_EVOLUTION_PLAYBOOK.md
docs/research/P5.8_SEMANTIC_ACTIVITY_UX.md
```

## Current cursor

```text
phase: 5
phase_name: natural non-blocking multi-chat product
phase_state: IN_PROGRESS
active_phase_record: docs/research/AGENTIC_PRODUCT_EVOLUTION_PLAYBOOK.md
active_slice: P5.7-conversation-scoped-preferences
active_slice_record: docs/research/P5.7_CONVERSATION_SCOPED_PREFERENCES.md
active_slice_state: IMPLEMENTED_FOCUSED_VALIDATION_REQUIRED
current_gate_type: HARD
blocking_validations: P5.7-ODOO-CONVERSATION-PREFERENCES
accepted_runtime_lineage: ba4ba00f9a913854a21b571cbb4559105347cca2 -> 8a4432dc9852eacc422b8c794b6613c75da702a9 -> f7f924ce944db86e896745fef83ea2fb6fd6583a -> b4fbb034e113a41c26db77cb274f2b3b30f6eee3 -> 32e836e7789ea72f3ba0d32fe6bdabbb092f5953 -> 3e2b38d68fe172cd2cf92d7794159f73476ac23d -> 8427c8849b1e1f3afa6337de1209a6027410c266 -> 720102f2a13af5240c779b07cc71ee65994a87b1 -> eb66e45447c4d64e1ebbb5e8322bffa759c12773
latest_accepted_evidence: docs/research/evidence/phase5/2026-08-29/P5.7-MODEL-REASONING-ACCEPTANCE-eb66e45.md
next_action: run P5.7-ODOO-CONVERSATION-PREFERENCES on clean current main in a disposable Odoo 18 Community database; repair and rerun before any broader P5.7 validation or P5.8 work
planned_successor_after_p5.7: P5.8-semantic-activity-reasoning-navigation-ux
planned_successor_record: docs/research/P5.8_SEMANTIC_ACTIVITY_UX.md
next_product_playbook: docs/research/AGENTIC_PRODUCT_EVOLUTION_PLAYBOOK.md
```

P5.6 is accepted. P5.7 is in progress: its model-family/reasoning-effort sub-slice is accepted through `eb66e45`. The remaining conversation-scoped preference mutation implementation is now present on `main`, but it is deliberately stopped at its first focused Odoo validation boundary. P5.8 remains planned only after all P5.7 validation is accepted.

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

Product direction: `AGENTIC_PRODUCT_EVOLUTION_PLAYBOOK.md` plus the accepted target supplement `P5.8_SEMANTIC_ACTIVITY_UX.md`.

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

## P5.6 ConversationContextManager — COMPLETE

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

The complete local Odoo/Codex/Chromium batch passed on exact checkpoint `720102f`:

```text
P5.6-ODOO-CONTEXT              PASS
P5.6-DETERMINISTIC-REGRESSION PASS
P5.6-FULL-ADDON-REGRESSION    PASS
P5-REAL-CONTINUITY            PASS
```

Evidence: `evidence/phase5/2026-08-29/P5.6-REAL-ACCEPTANCE-720102f.md`.

## P5.7 Conversation-scoped preferences — IN_PROGRESS / FOCUSED_GATE_REQUIRED

The model-family/model-variant/reasoning-effort preference sub-slice is accepted through `eb66e45`. Its immutable execution snapshot is format v2 and the exact explicit effort reaches all current App Server adapters.

```text
P5.7-ODOO-MODEL-REASONING-PREFERENCES PASS
P5.7-JS-MODEL-REASONING-PICKER       PASS
P5.3-FULL-ADDON-REGRESSION            PASS
P5.7-HOOT-ADDON                       PASS
P5-REAL-SETTINGS-SNAPSHOT             PASS
P5.1-BROWSER-SETTINGS-SNAPSHOT        PASS
```

Evidence: `evidence/phase5/2026-08-29/P5.7-MODEL-REASONING-ACCEPTANCE-eb66e45.md`.

The remaining conversation-scoped mutation implementation now adds:

```text
explicit temporary autonomy override per conversation
explicit response-language mode/fixed language per conversation
immutable response-language capture on each durable turn
projection into P5.6 session_settings
assistant.conversation.preferences read capability
assistant.conversation.set_autonomy PLAN capability with mandatory approval
assistant.conversation.set_response_language reversible PLAN capability
preview / precondition / execute / verify for both mutations
```

Implementation/validation record: `P5.7_CONVERSATION_SCOPED_PREFERENCES.md`.

No new P5.7 validation is accepted yet. The immediate hard stop is:

```text
P5.7-ODOO-CONVERSATION-PREFERENCES
```

Only after that focused Odoo gate passes may the slice prepare/run broader deterministic, full-addon and real product-path gates such as `P5-REAL-SESSION-POLICY` and the multilingual conversation-isolation observation required by the response-language contract.

## P5.8 Semantic activity/reasoning/navigation UX — PLANNED_AFTER_P5.7

Target specification: `P5.8_SEMANTIC_ACTIVITY_UX.md`.

This slice is intended to replace the user-visible event-log feel with a semantic work-item projection while preserving P3 durability/redaction. It covers stable operation correlation, compact live headline, grouped start/completion lifecycle, readable provider reasoning summaries only where safely supported, typed clickable Odoo/source references, progressive batch disclosure, configurable user/developer detail and complete Odoo-language localization of deterministic UI text.

It must remain separate from private/raw reasoning and from Phase-6 TaskPlan/effect authority. P5.8 is not implemented or validated yet.

---

# Current known limitations at the P5.7 focused validation boundary

- The new explicit conversation preference mutation code has not yet passed `P5.7-ODOO-CONVERSATION-PREFERENCES`; do not treat it as accepted product behavior until the gate is recorded.
- Broader P5.7 deterministic/full-addon/browser validation remains after the focused gate.
- Current public activity remains too close to raw capability lifecycle presentation; P5.8 is the planned semantic projection/UX repair.
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
- Raw provider output/private reasoning is never public activity; only explicitly safe readable reasoning summaries may later cross the P5.8 presentation seam.
- No parallel tool-authority registry is introduced.
- One active causal turn per conversation; independent conversations may run concurrently within scheduler capacity.
- Turn settings snapshots are immutable but revocable Odoo authorization stays dynamic.
- Conversation-scoped preference mutation never retroactively rewrites an already captured turn setting.
- Autonomy preference mutation is approval-bound and cannot create authority outside the existing host policy layers.
- P5.5 post-effect continuation has no PLAN authority.
- P5.6 context snapshots are derived from Odoo history and cannot authorize tools/effects.
- Deterministic user-visible Assistant text introduced by P5.8 must use Odoo localization semantics; semantic codes/arguments are protocol identity, not hard-coded English/Spanish strings.
- No GitHub Actions are used for roadmap validation under current instructions.

---

# Exact next action

Run `P5.7-ODOO-CONVERSATION-PREFERENCES` against clean current `main` on a disposable Odoo 18 Community database using test selector `/odoo_ai_assistant:TestAssistantConversationPreferences`. If it fails, repair only the responsible P5.7 conversation-preference layer and rerun. Do not launch the broader regression or start P5.8 until this focused gate passes.
