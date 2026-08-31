# Current implementation state

Current accepted lineage:

```text
Foundation/P0-P4 accepted through 8a4432dc9852eacc422b8c794b6613c75da702a9
P5.1 accepted through f7f924ce944db86e896745fef83ea2fb6fd6583a
P5.2 accepted through b4fbb034e113a41c26db77cb274f2b3b30f6eee3
P5.3 accepted through 32e836e7789ea72f3ba0d32fe6bdabbb092f5953
P5.4 accepted through 3e2b38d68fe172cd2cf92d7794159f73476ac23d
P5.5 accepted through 8427c8849b1e1f3afa6337de1209a6027410c266
P5.6 accepted through 720102f2a13af5240c779b07cc71ee65994a87b1
P5.7 complete through 074a71c29a6a6109ae7412e7b1f9850c4449e379
P5.8 complete through 688f569d441a40a4637ad6a23f111e584e18c955
```

Phase 5 is **COMPLETE**.

Phase 6 is **IMPLEMENTED AS A CANDIDATE BUT NOT ACCEPTED**. All P6.1-P6.6 implementation areas now exist, while the accumulated full/real validation remains pending. Implementation progress must not be confused with a green Phase-6 acceptance gate.

## 1. Product/deployment baseline

- Odoo 18 Community, self-hosted Linux.
- Addon: `addons/odoo_ai_assistant`, version `18.0.13.2.0`.
- Embedded runtime; browser talks only to Odoo.
- Odoo/PostgreSQL own conversations, messages, immutable turn settings, working checkpoints, effects, recovery state, EffectJournal and browser-safe state.
- Native `ir.cron` runs durable turns with bounded concurrency/backpressure.
- Business authority is always the originating effective user with `su=False`.
- Codex App Server is the current concrete reasoning provider using the host-configured primary session.
- Core planning/effect/recovery logic is provider-neutral so later providers can implement the same decision port.

## 2. Provider-neutral agent loop

The provider returns one strict `NextDecision` at a time:

```text
final_answer
task_plan_update
reasoning_capability_call
plan_step_proposal
```

The host owns capability resolution, schemas, budgets, TaskPlan rules, EffectPlan preparation, policy, approval, execution, verification and recovery semantics. Provider output is untrusted input, never execution authority.

Codex-specific code remains below this boundary and owns transport details such as App Server lifecycle, Structured Outputs translation, model/reasoning settings, provider failures and steer/interrupt behavior.

The first decision is the semantic route rather than a rigid intent class. It can return a direct
model answer, request the minimum authoritative Odoo reads, or begin genuinely multi-phase work.
A direct answer produces no generic public Thought activity. A short lookup can perform bounded
schema/query calls without creating a TaskPlan.

## 3. Planning modes and TaskPlan

P6.2 adds a provider-neutral planning strategy with a per-user selector captured immutably per turn:

```text
adaptive     default; begin directly and create/update TaskPlan when useful
deliberate   Plan mode; require an initial TaskPlan before capability/effect work
auto         host chooses adaptive vs deliberate from bounded structural complexity signals
```

The selector is not an autonomy level. It cannot change ACLs, available capabilities, approval policy or execution authority.

TaskPlan is user-visible progress only:

```text
goal
revision
revision_kind: initial | progress | replan
revision_summary
1..12 steps
  step_id
  title
  state: pending | in_progress | completed | blocked | skipped
  depends_on
```

Rules:

- no capability arguments/approval/execution authority;
- no private chain-of-thought;
- in adaptive mode, no TaskPlan for direct answers, short lookups, one batch operation or another
  artificial one-step wrapper;
- initial adaptive TaskPlans contain at least two meaningful dependent phases;
- exact monotonic revisions, with the next revision and legal kinds projected by the host as
  trusted contract state rather than mixed into untrusted transcript data;
- `progress` cannot silently change the plan structure;
- structural `replan` requires new host-observed evidence plus a short public revision summary;
- live turn status exposes the latest validated TaskPlan separately from effect approval;
- terminal/approval responses accept both legacy and current TaskPlan payloads;
- browser reconciliation chooses the newest validated revision and lets the authoritative final response win an equal-revision race;
- one final status refresh closes the completion edge where the last TaskPlan revision is persisted immediately before terminal state.

Legacy persisted TaskPlans and execution-settings snapshot formats remain readable.

## 4. Bounded EffectPlan

The product host supports up to **5** typed effect steps. Every step remains one `CapabilityDefinition` invocation with:

```text
step_id / depends_on
capability + version
validated arguments
preview
risk / effect / approval
precondition + binding fingerprints
recovery mode / recovery unit / journal classification
result + verification
semantic correlation keys
```

No generic program/script replaces typed capabilities.

Prepared EffectPlan format is now v3. Existing v1/v2 prepared data is conservatively readable/upgraded.

## 5. Recovery units

Host-derived recovery modes are:

```text
odoo_atomic
  consecutive Odoo-local effects intentionally share one transaction/recovery unit

segmented
  a trusted capability explicitly requires a durable internal unit boundary

external
  non-transactional intent is persisted before execution; interrupted outcome can remain uncertain
```

Provider text cannot choose or upgrade recovery semantics.

At every new unit the host preflights binding/preconditions/policy, reacquires the effect lock, rechecks Stop/redirect state, checkpoints durable intent/state and avoids blindly replaying a persisted in-flight unit.

## 6. EffectJournal and compensation

`odoo.ai.effect.journal` is Odoo-owned, bounded and short-lived:

```text
turn/user/company binding
capability/version/recovery-unit binding
bounded before/after/receipt evidence
7-day TTL + scheduled cleanup
system-only raw table access
owned-turn sanitized user projection
classification:
  reversible
  reconstructable
  irreversible
  external_or_unknown
```

The journal is not a backup and `reconstructable` is not automatic undo.

Existing P5.8 HOST-only compensators remain the safe reversion mechanism for supported reversible capabilities; successful compensation marks matching recent journal rows as reverted.

## 7. Budget families

The host resolves independent bounded families:

```text
SafetyBudget
ExplorationBudget
CostBudget
LatencyBudget
ResponseBudget
```

Remaining values sent to a provider are context only. Enforcement remains host-side.

## 8. Provider abstraction

The active seam is:

```text
Odoo host / AgentTurnService
          |
          v
 PlanningDecisionEngine
          |
          v
   NextDecisionEngine
      /    |     \
   Codex  future  future
  adapter adapter adapter
```

Provider-neutral core includes:

```text
planning strategy / TaskPlan / EffectPlan
capabilities and budgets
ACL / policy / approval
write barrier / recovery units
execution / verification
working transcript / EffectJournal
failure certainty
```

Provider adapters may specialize transport schemas, streaming, authentication/session transport, model knobs and provider-specific error mapping.

## 9. Capability framework

`CapabilityDefinition` remains the atomic executable contract. No unrestricted ORM method, SQL, Python, filesystem, shell or sudo authority is exposed to the model.

Future Skill/CapabilityProvider/ContextProvider/EvidenceProvider work should extend this framework instead of creating a second tool runtime.

## 10. Validation state

Accepted P5.8 evidence remains:

```text
research/evidence/phase5/2026-08-30/P5.8-REAL-ACCEPTANCE-688f569.md
```

The earlier P6.1/P6.3/P6.5 focused deterministic checkpoint was recorded at:

```text
research/evidence/phase6/2026-08-30/P6-FOCUSED-CHECKPOINT-1d6dc69.md
```

Later P6.2/P6.4/P6.6 code and tests are committed but their expensive final regression/real paths have not been executed in this environment. The final TaskPlan terminal/live reconciliation fix also has committed HOOT coverage (`phase6_task_plan_final_contract.test.js`) but is not claimed executed.

Accumulated Phase-6 real validation debt is:

```text
P6-REAL-MULTISTEP
P6-REAL-REPLAN
P6-REAL-EFFECT-ATOMICITY
P6-REAL-SEGMENTED-RECOVERY
P6-REAL-LOOP-BOUNDS
P6-REAL-EFFECT-JOURNAL
```

Formal cursor:

```text
P0 COMPLETE
P1 COMPLETE
P2 COMPLETE
P3 COMPLETE
P4 COMPLETE
P5 COMPLETE
P6 IMPLEMENTED_PENDING_PERIODIC_VALIDATION
  P6.1 TaskPlan vs EffectPlan            IMPLEMENTED_PENDING_PERIODIC_VALIDATION
  P6.2 adaptive/deliberate/replan        IMPLEMENTED_PENDING_PERIODIC_VALIDATION
  P6.3 bounded multi-step EffectPlan     IMPLEMENTED_PENDING_PERIODIC_VALIDATION
  P6.4 atomic vs segmented effects       IMPLEMENTED_PENDING_PERIODIC_VALIDATION
  P6.5 separate budgets                  IMPLEMENTED_PENDING_PERIODIC_VALIDATION
  P6.6 EffectJournal                     IMPLEMENTED_PENDING_PERIODIC_VALIDATION
P7+ NOT_ELIGIBLE
```

`research/PERIODIC_FULL_REGRESSION_RUNBOOK.md` is the canonical next acceptance step. Phase 7 should not begin until one exact Phase-6 candidate passes the applicable periodic full regression and real-product gates.
