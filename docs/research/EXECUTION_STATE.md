# Stabilization execution state

State format: 31
Updated: 2026-08-30

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
P5.7 complete through 074a71c29a6a6109ae7412e7b1f9850c4449e379
```

P5.8 implementation lineage is present on `main` but **not accepted**. Acceptance lineage therefore still stops at P5.7.

Roadmaps / active records:

```text
docs/research/AGENTIC_PRODUCT_EVOLUTION_PLAYBOOK.md
docs/research/P5.8_SEMANTIC_ACTIVITY_UX.md
docs/research/P5.8_IMPLEMENTATION.md
docs/research/P5.8_TURN_CONTROL_IMPLEMENTATION.md
docs/research/P5.8_NAVIGATION_IMPLEMENTATION.md
docs/research/P5.8_VALIDATION_RUNBOOK.md
docs/research/P5.8_CODEX_TEST_HANDOFF.md
```

## Current cursor

```text
phase: 5
phase_name: natural non-blocking multi-chat product
phase_state: IN_PROGRESS
active_phase_record: docs/research/AGENTIC_PRODUCT_EVOLUTION_PLAYBOOK.md
active_slice: P5.8-semantic-activity-interactive-control-navigation-compensation
active_slice_record: docs/research/P5.8_IMPLEMENTATION.md
active_slice_state: REAL_ENV_VALIDATION_REQUIRED
current_gate_type: HARD
blocking_validations: P5.8-DETERMINISTIC-REGRESSION, P5.8-FULL-ADDON-REGRESSION, P5.8-HOOT-ADDON, P5-REAL-SEMANTIC-ACTIVITY, P5-REAL-ACTIVITY-DEDUPE, P5-REAL-REASONING-SUMMARY, P5-REAL-ACTIVITY-I18N, P5-REAL-BATCH-DISCLOSURE, P5-REAL-ACTIVITY-RECONNECT, P5-REAL-NAVIGATION-REFS, P5-REAL-NAVIGATION-VIEW-MENU-SETTING, P5-REAL-FINAL-ANSWER-REFERENCES, P5-REAL-TURN-STOP, P5-REAL-TURN-INTERVENTIONS, P5-REAL-TURN-EFFECT-BOUNDARY-RACE, P5-REAL-COMPENSATION
accepted_runtime_lineage: ba4ba00f9a913854a21b571cbb4559105347cca2 -> 8a4432dc9852eacc422b8c794b6613c75da702a9 -> f7f924ce944db86e896745fef83ea2fb6fd6583a -> b4fbb034e113a41c26db77cb274f2b3b30f6eee3 -> 32e836e7789ea72f3ba0d32fe6bdabbb092f5953 -> 3e2b38d68fe172cd2cf92d7794159f73476ac23d -> 8427c8849b1e1f3afa6337de1209a6027410c266 -> 720102f2a13af5240c779b07cc71ee65994a87b1 -> eb66e45447c4d64e1ebbb5e8322bffa759c12773 -> 074a71c29a6a6109ae7412e7b1f9850c4449e379
p5_8_candidate_lineage_reviewed_through: bb1f6b1931057a7ab500a9c83629b72369c34aa2
latest_accepted_evidence: docs/research/evidence/phase5/2026-08-29/P5.7-REAL-ACCEPTANCE-074a71c.md
latest_executed_evidence: docs/research/evidence/phase5/2026-08-30/P5.8-FOCUSED-AND-LANGUAGE-faf21f4.md
next_action: pull exact current main into the disposable Odoo 18 validation environment and execute docs/research/P5.8_CODEX_TEST_HANDOFF.md / P5.8_VALIDATION_RUNBOOK.md; run deterministic/unit, full-addon and complete HOOT gates first, then the full semantic/reasoning/i18n/batch/reconnect/navigation/final-reference/Stop/intervention/effect-boundary/compensation real chain; do not mark P5.8 COMPLETE or start P6 until every required HARD gate is reviewed
planned_successor_after_p5.8: Phase 6 bounded multi-step EffectPlan / TaskPlan work
next_product_playbook: docs/research/AGENTIC_PRODUCT_EVOLUTION_PLAYBOOK.md
```

`p5_8_candidate_lineage_reviewed_through` records the final code/test checkpoint prepared before this cursor-only update. Validation must always record the actual pulled `TESTED_SHA`; it must not assume that checkpoint is still HEAD.

## Phase summary

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
  P5.8 REAL_ENV_VALIDATION_REQUIRED
P6+ NOT ELIGIBLE
```

## P5.8 implementation present

Current P5.8 code extends the accepted P3 live stream/P5 host loop without changing business authority.

### Semantic activity / readable reasoning

```text
host-owned activity_id lifecycle correlation
semantic reducer/upsert + replay dedupe
compact changing live headline + completed duration/step count
compact | normal | detailed | diagnostic presentation
bounded per-user presentation preferences
Odoo-localized deterministic labels
separate bounded readable reasoning-summary channel
raw item/reasoning/textDelta never projected
```

### Interactive turn control

```text
odoo.ai.turn.intervention durable ordered correction rows
client_intervention_id idempotency/conflict protection
strict intervention count/byte budgets
queued correction consumed before provider decision
running correction persisted before provider control
best-effort Codex turn/steer(expectedTurnId) for a live subturn
interrupt/restart fallback from durable Odoo state when steer is unavailable
same-turn approval supersession with approval.rejected
current-chat Stop with durable Odoo cancellation + best-effort turn/interrupt
partial streamed answer retained as Interrumpido
stale decision rejection + final control/write-barrier serialization
```

Provider thread/turn IDs never cross into browser state. Provider steering is a responsiveness optimization, never durable authority.

### Contextual navigation

Supported public kinds:

```text
odoo_record
odoo_model
odoo_action
odoo_view
odoo_menu
odoo_setting
```

`odoo.resolve_navigation` is a read-only `CapabilityDefinition` that accepts semantic query text rather than authoritative concrete IDs. Odoo resolves bounded current models/actions/views/visible menus/installed settings under the effective `su=False` user.

Streaming activity and final answers can carry closed structured references. Every click returns the typed identity to `/odoo_ai/v1/public-references`; Odoo revalidates current existence, ACL/record rules, groups/menu visibility and settings schema before returning a closed descriptor. Model-generated arbitrary Odoo URLs/routes are never navigation authority.

### Safe compensation

Explicit HOST-only compensators currently cover:

```text
odoo.record.patch       -> odoo.record.patch.revert
odoo.record.archive     -> odoo.record.archive.revert
odoo.record.unarchive   -> odoo.record.unarchive.revert
```

They reuse `CapabilityExecutor`, run business access under the effective user, require optimistic current-state match, restore only bounded captured prior state and verify the inverse before reversion is recorded complete. There is no generic PostgreSQL rollback.

## Prepared automated coverage

Committed deterministic/Odoo/HOOT tests now cover or extend:

- semantic activity correlation/replay/transient filtering;
- readable reasoning-summary shape/privacy;
- live public activity with contextual references;
- record/model/action/view/menu/setting closed reference contracts;
- malformed/additional-key/deleted/revoked reference failure;
- menu visibility and installed settings discovery;
- browser revalidation before `actionService` and arbitrary-route rejection;
- streaming and final structured navigation references;
- composer idle/send/Stop/correct modes, processing textarea editability and accessibility labels;
- durable intervention ordering, idempotency/conflict and ownership isolation;
- explicit queued and running intervention persistence plus 16-item count limit;
- approval supersession on the same turn;
- current-chat Stop isolation and interrupted partial answer;
- Codex `turn/steer(expectedTurnId)` and interrupt/restart fallback;
- late redirect rejection after write barrier;
- patch compensation, later-change conflict refusal, archive/unarchive compensation and permission revalidation.

These tests are **prepared, not claimed executed** on the current implementation lineage by this GitHub-only work.

The earlier focused P5.8/language execution on `faf21f4809cf04020e795a8b824b3197b56c4ace` remains useful evidence but predates the current interactive-control/navigation/compensation implementation and is not acceptance evidence for the present candidate.

## Required P5.8 gate chain

Run `P5.8_CODEX_TEST_HANDOFF.md` and `P5.8_VALIDATION_RUNBOOK.md` on one coherent materially unchanged candidate:

```text
P5.8-DETERMINISTIC-REGRESSION
  -> P5.8-FULL-ADDON-REGRESSION
  -> P5.8-HOOT-ADDON
  -> P5-REAL-SEMANTIC-ACTIVITY
  -> P5-REAL-ACTIVITY-DEDUPE
  -> P5-REAL-REASONING-SUMMARY
  -> P5-REAL-ACTIVITY-I18N
  -> P5-REAL-BATCH-DISCLOSURE
  -> P5-REAL-ACTIVITY-RECONNECT
  -> P5-REAL-NAVIGATION-REFS
  -> P5-REAL-NAVIGATION-VIEW-MENU-SETTING
  -> P5-REAL-FINAL-ANSWER-REFERENCES
  -> P5-REAL-TURN-STOP
  -> P5-REAL-TURN-INTERVENTIONS
  -> P5-REAL-TURN-EFFECT-BOUNDARY-RACE
  -> P5-REAL-COMPENSATION
```

`P5-REAL-REASONING-SUMMARY` may record provider support as reviewed `UNSUPPORTED` only under the fallback rule in the validation runbook: semantic host activity must remain correct and no raw/private reasoning may reach browser state.

## Invariants carried forward

- Odoo remains persistence, operational and navigation authority.
- Business capabilities and compensation run under the effective user with `su=False`.
- `CapabilityDefinition` remains atomic executable authority.
- Provider/context/presentation/intervention text never grants effect authority.
- P5.5 durable write barrier, verification and post-effect certainty remain authoritative.
- Stop/correction cannot bypass policy, approval, ACL, preview, verification or recovery.
- The advisory effect lock orders only final control versus barrier commit and is not held across provider/business work.
- Provider thread/turn IDs remain host-internal.
- Raw provider output/private chain-of-thought is never public activity.
- Answer deltas, semantic activity and readable reasoning summaries remain independent presentation channels.
- All public navigation references are freshly revalidated by Odoo; model-generated routes are never trusted.
- Presentation preferences cannot weaken ACL/policy/approval/audit/recovery.
- P5.6/P5.7 turn settings/context remain immutable as already accepted.
- One canonical effect step remains the P5 limit; bounded multi-step effects remain Phase 6.
- No GitHub Actions are used for roadmap validation under current repository instructions.

## Exact stop rule

P5.8 implementation is at the validation boundary. Do not start Phase 6 merely because code/tests/docs are present. A failed HARD gate creates a P5.8 repair slice. Only one reviewed green required chain makes P5.8 `COMPLETE` and Phase 6 eligible.
