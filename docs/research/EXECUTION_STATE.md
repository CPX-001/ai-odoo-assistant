# Stabilization execution state

State format: 34
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
P5.8 complete through 688f569d441a40a4637ad6a23f111e584e18c955
```

P5.8 is **accepted and COMPLETE**. The repaired candidate passed the complete automated and real-environment chain, including the strengthened semantic-activity gate.

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
active_slice_state: COMPLETE
current_gate_type: NONE
blocking_work: none
blocking_validations_after_repair: none
accepted_runtime_lineage: ba4ba00f9a913854a21b571cbb4559105347cca2 -> 8a4432dc9852eacc422b8c794b6613c75da702a9 -> f7f924ce944db86e896745fef83ea2fb6fd6583a -> b4fbb034e113a41c26db77cb274f2b3b30f6eee3 -> 32e836e7789ea72f3ba0d32fe6bdabbb092f5953 -> 3e2b38d68fe172cd2cf92d7794159f73476ac23d -> 8427c8849b1e1f3afa6337de1209a6027410c266 -> 720102f2a13af5240c779b07cc71ee65994a87b1 -> eb66e45447c4d64e1ebbb5e8322bffa759c12773 -> 074a71c29a6a6109ae7412e7b1f9850c4449e379
p5_8_last_green_automated_candidate: 0b0ac2d2c8fb25523c2e6e9c3808d3c702cede80
latest_accepted_evidence: docs/research/evidence/phase5/2026-08-30/P5.8-REAL-ACCEPTANCE-688f569.md
latest_executed_evidence: docs/research/evidence/phase5/2026-08-30/P5.8-REAL-ACCEPTANCE-688f569.md
next_action: begin Phase 6 only under a separate explicit execution scope
planned_successor_after_p5.8: Phase 6 bounded multi-step EffectPlan / TaskPlan work
next_product_playbook: docs/research/AGENTIC_PRODUCT_EVOLUTION_PLAYBOOK.md
```

The previous automated PASS remains valid evidence for `0b0ac2d`; it is not transferable to a materially changed repaired candidate. The actual repaired SHA must be recorded and retested.

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
  P5.8 COMPLETE
P6 ELIGIBLE / NOT STARTED
```

## P5.8 state by subsystem

### Semantic activity / readable reasoning

Implemented foundation:

```text
host-owned activity_id lifecycle correlation
frontend reducer/upsert + replay dedupe
compact changing live headline + completed duration/step count
compact | normal | detailed | diagnostic presentation profiles
bounded per-user presentation preferences
Odoo-localized deterministic labels
separate bounded readable-reasoning-summary channel
raw item/reasoning/textDelta never projected
```

Resolved semantic repair:

```text
explicit host-owned semantic grouping/context is carried end to end
normal mode uses localized business headlines rather than capability titles
independent operations remain independent unless the host supplies correlation
progress/result summaries are emitted only from host-known facts
```

The observed technical activity dump for a request such as `¿puedes crear 200 presupuestos demo?` is explicitly a P5.8 failure. `P5-REAL-SEMANTIC-ACTIVITY` must reject that behavior.

This is not Phase 6 TaskPlan work. Phase 6 may add a separate task-plan surface, but P5.8 must already turn lifecycle facts into coherent normal-user semantic activity.

### Interactive turn control

Current implementation includes:

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

Explicit HOST-only compensators cover:

```text
odoo.record.patch       -> odoo.record.patch.revert
odoo.record.archive     -> odoo.record.archive.revert
odoo.record.unarchive   -> odoo.record.unarchive.revert
```

They reuse `CapabilityExecutor`, run business access under the effective user, require optimistic current-state match, restore only bounded captured prior state and verify the inverse before reversion is recorded complete. There is no generic PostgreSQL rollback.

## Executed P5.8 automated evidence

The complete automated battery was executed on `0b0ac2d2c8fb25523c2e6e9c3808d3c702cede80`:

```text
P5.8-DETERMINISTIC-REGRESSION  PASS (242 dependency-light tests plus JS/static checks)
P5.8-FULL-ADDON-REGRESSION    PASS (182 selected tests, 0 failures/errors)
P5.8-HOOT-ADDON               PASS (139 tests)
```

See `docs/research/evidence/phase5/2026-08-30/P5.8-AUTOMATED-GATES-0b0ac2d.md`.

Those gates correctly prove the contracts they tested. They did not contain a strong enough product assertion to reject the technical normal-mode lifecycle dump, so the semantic gap was not caught by them. The runbook now requires that regression coverage.

The earlier focused P5.8/language execution on `faf21f4809cf04020e795a8b824b3197b56c4ace` remains useful evidence but explicitly did not accept the complete semantic/navigation/batch/reconnect chain.

## Required P5.8 order now

```text
1. repair semantic work-item projection as one coherent P5.8 slice
2. add regression coverage that rejects the technical lifecycle dump in normal mode
3. rerun complete automated battery on repaired SHA
4. P5-REAL-SEMANTIC-ACTIVITY
5. P5-REAL-ACTIVITY-DEDUPE
6. P5-REAL-REASONING-SUMMARY
7. P5-REAL-ACTIVITY-I18N
8. P5-REAL-BATCH-DISCLOSURE
9. P5-REAL-ACTIVITY-RECONNECT
10. P5-REAL-NAVIGATION-REFS
11. P5-REAL-NAVIGATION-VIEW-MENU-SETTING
12. P5-REAL-FINAL-ANSWER-REFERENCES
13. P5-REAL-TURN-STOP
14. P5-REAL-TURN-INTERVENTIONS
15. P5-REAL-TURN-EFFECT-BOUNDARY-RACE
16. P5-REAL-COMPENSATION
```

`P5-REAL-REASONING-SUMMARY` may record provider support as reviewed `UNSUPPORTED` only under the fallback rule in the validation runbook: semantic host activity must remain useful/correct and no raw/private reasoning may reach browser state.

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
- Roadmap slices should be the largest coherent feasible product changes, not artificial micro-slices; commit/file granularity does not define slice boundaries.

## Exact stop rule

Do not start Phase 6. P5.8 first needs the semantic-work-item implementation repair and the complete repaired-candidate HARD validation chain. A failed HARD gate creates repair work inside the same coherent P5.8 slice unless a genuine authority/environment boundary requires a split.
