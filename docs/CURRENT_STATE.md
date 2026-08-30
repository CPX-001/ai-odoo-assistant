# Current implementation state

Current accepted product lineage on `main` remains:

```text
Foundation/P0-P4 accepted through 8a4432dc9852eacc422b8c794b6613c75da702a9
P5.1 accepted through f7f924ce944db86e896745fef83ea2fb6fd6583a
P5.2 accepted through b4fbb034e113a41c26db77cb274f2b3b30f6eee3
P5.3 accepted through 32e836e7789ea72f3ba0d32fe6bdabbb092f5953
P5.4 accepted through 3e2b38d68fe172cd2cf92d7794159f73476ac23d
P5.5 accepted through 8427c8849b1e1f3afa6337de1209a6027410c266
P5.6 accepted through 720102f2a13af5240c779b07cc71ee65994a87b1
P5.7 model/reasoning preference sub-slice accepted through eb66e45447c4d64e1ebbb5e8322bffa759c12773
P5.7 complete through 074a71c29a6a6109ae7412e7b1f9850c4449e379
```

P5.8 is **partially implemented and currently IN_PROGRESS**. Interactive turn control, safe compensation, contextual navigation, semantic correlation/presentation infrastructure and readable-summary channels exist, but product review found that normal semantic activity is still too close to a technical capability lifecycle log for complex turns. That semantic work-item gap must be repaired before P5.8 enters final real-environment acceptance.

The authoritative cursor is `research/EXECUTION_STATE.md`; implementation detail is in `research/P5.8_IMPLEMENTATION.md`; product target is `research/P5.8_SEMANTIC_ACTIVITY_UX.md`; required repair/validation is in `research/P5.8_VALIDATION_RUNBOOK.md` and `research/P5.8_CODEX_TEST_HANDOFF.md`.

## 1. Product/deployment baseline

- Odoo 18 Community, self-hosted Linux.
- Addon: `addons/odoo_ai_assistant`, version `18.0.10.24.0` on the current P5.8 lineage.
- Embedded runtime; browser talks only to Odoo, not a sidecar/provider service.
- Odoo/PostgreSQL own conversations, messages, turns, effect state, interventions, private working checkpoints and browser-safe live/presentation state.
- Native `ir.cron` runs durable turns.
- Business authority is the originating effective user with `su=False`.
- Primary provider is local Codex App Server using the host-configured primary session.
- Product target remains one global general Assistant; see `PRODUCT_VISION.md`.

## 2. Host-owned agent loop and effects

ADR-019/current code owns orchestration. The provider returns one strict `NextDecision` per call:

```text
final_answer
reasoning_capability_call
plan_step_proposal
```

Odoo resolves capabilities, validates schemas/policy/authority and executes through the host-owned capability framework. Provider data is untrusted input, never authority.

Accepted P5.5 effect lifecycle remains:

```text
one canonical PlanStepProposal
 -> prepare / preview / preconditions
 -> policy / approval
 -> revalidate
 -> durable write barrier
 -> execute under effective user
 -> verify
 -> authoritative verified-effect receipt
 -> REASONING-only post-effect continuation
 -> natural final answer
```

Current effect limit remains one canonical step. Bounded multi-step `EffectPlan`/TaskPlan is Phase 6 work and must not be conflated with P5.8 activity or intervention sequencing.

## 3. Capability framework

`CapabilityDefinition` remains the atomic executable contract. Current core providers include:

```text
assistant_preferences
odoo_query
odoo_actions
odoo_batch
odoo_runtime
odoo_navigation
odoo_compensations (HOST-only inverses)
odoo_unarchive
```

`odoo.resolve_navigation` is a normal read-only reasoning capability. Compensators such as `odoo.record.patch.revert`, `odoo.record.archive.revert` and `odoo.record.unarchive.revert` are HOST-only definitions in the same registry and are never revealed as model-callable tools.

No unrestricted ORM methods, SQL, Python, filesystem, shell or sudo authority is exposed to the model. External provider/Skill/Context/Evidence contracts remain later roadmap work.

## 4. Conversation/context/settings

P5.6 immutable per-turn conversation context and P5.7 conversation/model/reasoning/language settings remain accepted. Current turns snapshot bounded execution settings and derived context while ACLs, record rules and capability availability remain dynamically revocable.

P5.8 presentation preferences are per-user and explicitly non-authoritative. They can change visible activity detail, technical-name display, transient filtering, reasoning-summary display and progressive-disclosure page size without changing business policy or an already captured turn's execution authority.

## 5. P5.8 semantic activity — foundation present, richer work items still missing

The accepted P3 live store now feeds a semantic presentation layer:

- host-generated `activity_id` correlates start/completion/failure for one operation;
- repeated independent calls remain separate;
- provider reasoning passes have their own correlation identity;
- reconnect/replay reduction is idempotent by event sequence/activity identity;
- compact/normal/detailed/diagnostic presentation profiles are supported;
- deterministic wording uses Odoo localization semantics;
- readable provider summaries use only bounded `summaryTextDelta`; raw/private reasoning is never projected;
- capability/result references may appear as compact browser-safe chips without becoming business authority.

This infrastructure does **not yet fully satisfy** `P5.8_SEMANTIC_ACTIVITY_UX.md`. In complex turns, normal mode can still expose or be dominated by capability lifecycle titles such as:

```text
Inspect Odoo write schema · sale.order
Inspect Odoo query schema · res.partner
Query Odoo records · res.partner
Mutate multiple Odoo records · sale.order
```

The intended P5.8 behavior is a small coherent set of host-grounded semantic work items, for example conceptually:

```text
Analizando la petición
Preparando 200 presupuestos demo
  Consultando clientes existentes
Creando presupuestos
  <grounded progress when known>
Verificando resultados
  <grounded verified result summary>
```

The repair must introduce enough host-owned semantic grouping/context — e.g. semantic parent/group keys, operation/category, translated headline code + bounded args, grounded progress/result summaries — or an equivalent simpler contract. It must not group by string equality or let model prose fabricate progress.

Diagnostic mode may retain technical detail. Normal mode must not be a capability lifecycle dump.

This gap belongs to P5.8. It is not deferred to Phase 6 TaskPlan.

## 6. P5.8 interactive turn control

The browser treats the active conversation/turn as the control boundary.

Composer behavior is:

```text
no active turn + empty draft      -> disabled
no active turn + text             -> Enviar mensaje
processing + empty draft          -> Detener respuesta (square Stop icon)
processing + text                 -> Corregir instrucción
awaiting approval + text          -> Corregir instrucción / supersede old plan
```

The textarea remains editable while ordinary reasoning is running.

Corrections are not second ordinary turns. `odoo.ai.turn.intervention` persists a bounded ordered sequence linked to the same turn/conversation/user/company with `client_intervention_id` duplicate protection. Count and byte budgets are enforced.

Runtime behavior is host-owned:

```text
persist intervention in Odoo first
 -> queued: consume before first decision
 -> running + live Codex subturn: best-effort turn/steer(expectedTurnId)
 -> no steer / no live subturn: interrupt disposable subturn and restart next decision from durable Odoo state
 -> re-check sequence before accepting provider decision / before effect barrier
```

Provider thread/turn IDs never reach the browser.

If a correction arrives while an approval is pending, Odoo records `approval.rejected`, clears the executable old plan and requeues/resumes the same durable turn. The old plan cannot be silently approved or executed.

Stop reuses durable Odoo cancellation. Only the active chat's turn UUID is cancelled; other conversation scopes continue. A partial answer already streamed is preserved as an Assistant message marked `Interrumpido`. Stop after an effect barrier does not claim rollback of already executed business effects.

## 7. P5.8 safe compensation

There is no database-wide or magical rollback. Compensation is an explicit host-side action after a verified reversible effect.

Initially supported effect families are:

```text
odoo.record.patch
odoo.record.archive
odoo.record.unarchive
```

The original preview contains only the bounded prior values needed by the matching compensator. Before restoration the host:

1. revalidates the current effective user's ACL/record rules;
2. verifies the record still matches the previously verified post-effect value;
3. refuses to overwrite later changes (`capability_compensation_precondition_changed`);
4. executes the explicit HOST-only compensator;
5. re-reads and verifies the restored value;
6. only then marks reversion complete.

The UI offers `Revertir cambios` only when the host declares a safe compensator and asks for explicit confirmation. Unavailable/conflicting/unauthorized reversions are reported without claiming success.

## 8. P5.8 contextual navigation

Supported public reference kinds are:

```text
odoo_record
odoo_model
odoo_action
odoo_view
odoo_menu
odoo_setting
```

`odoo.resolve_navigation` accepts semantic query text, never authoritative concrete IDs. Odoo searches bounded current models/actions/views/visible menus/installed settings under the effective user.

Discovery is not navigation authority. Every click is sent back to `/odoo_ai/v1/public-references`, which revalidates exact reference shape, current existence, ACL/record rules, current menu/group visibility and current settings schema before returning a closed descriptor. The frontend builds an Odoo action only from that descriptor. Raw model-authored URLs/routes are never executed.

Navigation references are available both:

- inside correlated streaming activity;
- as a structured `references` collection rendered below the final answer.

A stale/revoked/deleted target fails closed with a discreet notice and never reaches `actionService`.

Unknown OCA/custom business models still use generic current-schema/access-driven record/model presentation where eligible.

## 9. Queue/concurrency/failure invariants

Accepted P5.1-P5.5 behavior remains authoritative:

- per-conversation frontend scopes;
- one active causal turn per conversation;
- cross-conversation concurrency within scheduler capacity;
- bounded scheduler/backpressure/fairness;
- explicit approval/failure/recovery surfaces;
- one authoritative final Assistant message;
- uncertain post-write outcomes are never blindly retried as effect-safe.

P5.8 presentation/navigation failure cannot change business-effect success/authorization. Turn interventions cannot bypass capability validation/policy/approval/verification.

## 10. Retrieval/RAG and technical operations

There is still no general embedded Evidence/RAG provider. Later retrieval should combine current Odoo/runtime/schema/configuration, source/XML, logs, company knowledge/files, lexical/semantic retrieval and web evidence as appropriate.

Not currently exposed to reasoning:

```text
module install/update
odoo.conf modification
service/process restart
PostgreSQL administration
source-code modification
generic command execution
general web search
```

Later privileged technical operations require explicit capabilities and privilege-boundary validation.

## 11. Executed P5.8 validation and current roadmap state

Historical automated P5.8 evidence exists for checkpoint `0b0ac2d2c8fb25523c2e6e9c3808d3c702cede80`:

```text
P5.8-DETERMINISTIC-REGRESSION  PASS (242 dependency-light tests plus JS/static checks)
P5.8-FULL-ADDON-REGRESSION    PASS (182 selected tests)
P5.8-HOOT-ADDON               PASS (139 tests)
```

That evidence remains valid for the tested checkpoint, but the tests were not strong enough to reject the now-observed normal-mode technical lifecycle dump. A semantic-work-item repair is therefore required and the affected automated gates must be rerun on the repaired SHA.

Formal roadmap state:

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
  P5.8 IN_PROGRESS
P6+ NOT ELIGIBLE
```

Required P5.8 order now:

```text
semantic work-item repair
P5.8-DETERMINISTIC-REGRESSION on repaired SHA
P5.8-FULL-ADDON-REGRESSION on repaired SHA
P5.8-HOOT-ADDON on repaired SHA
P5-REAL-SEMANTIC-ACTIVITY
P5-REAL-ACTIVITY-DEDUPE
P5-REAL-REASONING-SUMMARY
P5-REAL-ACTIVITY-I18N
P5-REAL-BATCH-DISCLOSURE
P5-REAL-ACTIVITY-RECONNECT
P5-REAL-NAVIGATION-REFS
P5-REAL-NAVIGATION-VIEW-MENU-SETTING
P5-REAL-FINAL-ANSWER-REFERENCES
P5-REAL-TURN-STOP
P5-REAL-TURN-INTERVENTIONS
P5-REAL-TURN-EFFECT-BOUNDARY-RACE
P5-REAL-COMPENSATION
```

The stronger `P5-REAL-SEMANTIC-ACTIVITY` gate explicitly fails a normal-mode chronological capability dump, duplicate lifecycle rows, repeated raw tool titles, generic phase-only activity without meaningful operation context, invented progress or private reasoning.

Only a reviewed green repaired-candidate chain makes Phase 6 eligible.
