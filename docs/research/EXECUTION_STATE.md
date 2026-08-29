# Stabilization execution state

State format: 27
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
P5.7 complete through 074a71c29a6a6109ae7412e7b1f9850c4449e379
```

P5.8 implementation lineage is present but **not accepted**. Acceptance lineage therefore still stops at P5.7.

Roadmaps / active records:

```text
docs/research/AGENTIC_PRODUCT_EVOLUTION_PLAYBOOK.md
docs/research/P5.8_SEMANTIC_ACTIVITY_UX.md
docs/research/P5.8_IMPLEMENTATION.md
docs/research/P5.8_VALIDATION_RUNBOOK.md
```

## Current cursor

```text
phase: 5
phase_name: natural non-blocking multi-chat product
phase_state: IN_PROGRESS
active_phase_record: docs/research/AGENTIC_PRODUCT_EVOLUTION_PLAYBOOK.md
active_slice: P5.8-semantic-activity-reasoning-navigation-ux
active_slice_record: docs/research/P5.8_IMPLEMENTATION.md
active_slice_state: REAL_ENV_VALIDATION_REQUIRED
current_gate_type: HARD
blocking_validations: P5.8-DETERMINISTIC-REGRESSION, P5.8-FULL-ADDON-REGRESSION, P5.8-HOOT-ADDON, P5-REAL-SEMANTIC-ACTIVITY, P5-REAL-ACTIVITY-DEDUPE, P5-REAL-REASONING-SUMMARY, P5-REAL-ACTIVITY-I18N, P5-REAL-NAVIGATION-REFS, P5-REAL-BATCH-DISCLOSURE, P5-REAL-ACTIVITY-RECONNECT
accepted_runtime_lineage: ba4ba00f9a913854a21b571cbb4559105347cca2 -> 8a4432dc9852eacc422b8c794b6613c75da702a9 -> f7f924ce944db86e896745fef83ea2fb6fd6583a -> b4fbb034e113a41c26db77cb274f2b3b30f6eee3 -> 32e836e7789ea72f3ba0d32fe6bdabbb092f5953 -> 3e2b38d68fe172cd2cf92d7794159f73476ac23d -> 8427c8849b1e1f3afa6337de1209a6027410c266 -> 720102f2a13af5240c779b07cc71ee65994a87b1 -> eb66e45447c4d64e1ebbb5e8322bffa759c12773 -> 074a71c29a6a6109ae7412e7b1f9850c4449e379
p5_8_implementation_checkpoint: bfc774dd0ad1992e71ab05f75c4897d088dc7fe5
latest_accepted_evidence: docs/research/evidence/phase5/2026-08-29/P5.7-REAL-ACCEPTANCE-074a71c.md
latest_executed_evidence: docs/research/evidence/phase5/2026-08-29/P5.7-REAL-ACCEPTANCE-074a71c.md
next_action: pull exact current main into the disposable Odoo 18 validation environment and execute docs/research/P5.8_VALIDATION_RUNBOOK.md; process local/full-addon/HOOT results first, then the real semantic/reasoning/i18n/navigation/batch/reconnect gates; do not mark P5.8 COMPLETE or start P6 until the HARD gates are reviewed
planned_successor_after_p5.8: Phase 6 bounded multi-step EffectPlan / TaskPlan work
next_product_playbook: docs/research/AGENTIC_PRODUCT_EVOLUTION_PLAYBOOK.md
```

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

## P5.8 implementation now present

P5.8 extends the accepted P3 live stream and P5 frontend without changing business authority. Current implementation includes:

```text
host-owned activity_id correlation across capability start/completion/failure
host-owned correlation and terminal closure for initial and post-effect provider reasoning passes
semantic reducer/upsert with replay dedupe and semantic step counting
compact changing live headline + collapsed completed duration
compact / normal / detailed / diagnostic activity presentation profiles
configurable transient threshold, batch page size and bounded rendering ceilings
Odoo-localized deterministic semantic labels with technical identifiers hidden by default
separate bounded readable-reasoning-summary live channel
explicit rejection/non-projection of raw item/reasoning/textDelta
typed odoo_record / odoo_model references
fresh ACL/existence revalidation immediately before navigation
generic effective-schema/access-driven record presentation
safe result-identity projection from bounded capability results
five-row progressive disclosure with hard browser limit and list/model fallback
```

Implementation details and the deliberate presenter simplification are recorded in `P5.8_IMPLEMENTATION.md`.

Prepared deterministic/Odoo/HOOT tests cover correlation, repeated identical operations, provider completion/failure, transient filtering, replay, user preference isolation, reasoning-summary bounds/privacy, current ACL reference validation, generic field presentation, read/mutation result references and disclosure limits.

**These tests have not been represented as executed in this run.** The environment available to this repository-editing session does not provide the disposable Odoo/Codex/Chromium execution path, and repository instructions prohibit substituting GitHub Actions. Therefore no P5.8 gate is marked PASS.

## Required P5.8 gate chain

Run `P5.8_VALIDATION_RUNBOOK.md` on one coherent materially unchanged checkpoint:

```text
P5.8-DETERMINISTIC-REGRESSION
  -> P5.8-FULL-ADDON-REGRESSION
  -> P5.8-HOOT-ADDON
  -> P5-REAL-SEMANTIC-ACTIVITY
  -> P5-REAL-ACTIVITY-DEDUPE
  -> P5-REAL-REASONING-SUMMARY
  -> P5-REAL-ACTIVITY-I18N
  -> P5-REAL-NAVIGATION-REFS
  -> P5-REAL-BATCH-DISCLOSURE
  -> P5-REAL-ACTIVITY-RECONNECT
```

`P5-REAL-REASONING-SUMMARY` may record the provider feature as unsupported only if the reviewed product observation proves the privacy-safe fallback: no raw/private reasoning reaches browser state and semantic host activity remains correct. Unsupported provider output is not itself a reason to invent or expose a private reasoning channel.

## Invariants carried forward

- Odoo remains persistence and operational authority.
- Business capabilities run under the effective user with `su=False`.
- `CapabilityDefinition` remains atomic executable authority.
- Provider/context/presentation data never grants effect authority.
- P5.5 durable write barrier, verification and post-effect certainty remain authoritative.
- Raw provider output/private chain-of-thought is never public activity.
- Answer deltas, semantic activity and readable reasoning summaries are independent presentation channels.
- Typed references are revalidated under current Odoo access before navigation; model-generated arbitrary routes are never trusted.
- Presentation preferences cannot weaken ACL, policy, approval, audit or recovery requirements.
- P5.6/P5.7 turn settings/context remain immutable as already accepted.
- One canonical effect step remains the P5 limit; multi-step effects are Phase 6.
- No GitHub Actions are used for roadmap validation under current repository instructions.

## Exact stop rule

P5.8 implementation work is at the validation boundary. Do not start Phase 6 merely because the code is present. First execute and review the P5.8 gate chain. A failed HARD gate creates a P5.8 repair slice; a clean accepted chain marks P5.8 `COMPLETE` and only then makes Phase 6 eligible.
