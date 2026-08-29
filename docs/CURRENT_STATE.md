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

P5.8 semantic activity/reasoning/navigation UX is now **implemented but not accepted**. Its exact cursor is `research/EXECUTION_STATE.md`; implementation detail is in `research/P5.8_IMPLEMENTATION.md` and validation requirements are in `research/P5.8_VALIDATION_RUNBOOK.md`.

## 1. Product/deployment baseline

- Odoo 18 Community, self-hosted Linux.
- Addon: `addons/odoo_ai_assistant`, version `18.0.10.23.0` on the P5.8 implementation lineage.
- Embedded runtime; browser talks to Odoo, not a sidecar.
- Odoo/PostgreSQL own conversations, messages, turns, effect state, private working checkpoints and public/live presentation state.
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

Current effect limit remains one canonical step. Bounded multi-step `EffectPlan`/TaskPlan is Phase 6 work and must not be conflated with P5.8 semantic activity.

## 3. Capability framework

`CapabilityDefinition` remains the atomic executable contract. Current core providers include:

```text
assistant_preferences
odoo_query
odoo_actions
odoo_batch
odoo_runtime
```

No unrestricted ORM methods, SQL, Python, filesystem, shell or sudo authority is exposed to the model. External provider/Skill/Context/Evidence contracts remain later roadmap work.

## 4. Conversation/context/settings

P5.6 immutable per-turn conversation context and P5.7 conversation/model/reasoning/language settings remain accepted. Current turns snapshot bounded execution settings and derived context while ACLs, record rules and capability availability remain dynamically revocable.

P5.8 presentation preferences are per-user and explicitly non-authoritative. They can change visible activity detail, technical-name display, transient filtering, reasoning-summary display and progressive-disclosure page size without changing business policy or an already captured turn's execution authority.

## 5. P5.8 semantic activity implementation

The old public event-log feel now has a semantic projection layer above the accepted P3 live store.

### Correlation and lifecycle

- capability lifecycle start/completion/failure shares a host-generated versioned `activity_id`;
- identical independent calls get independent IDs;
- initial provider reasoning and post-effect synthesis use distinct correlated IDs;
- provider completion/failure closes its matching semantic work item;
- reconnect/replay reduction is idempotent by sequence and activity identity.

### Presentation

Frontend projection supports:

```text
compact
normal (default)
detailed
diagnostic
```

The compact running header follows the latest meaningful semantic item. Completed activity collapses to total elapsed time plus semantic step count. Sub-threshold successful verification can be hidden from normal history while failures/approval remain visible. Technical names are hidden by default.

Deterministic semantic text uses Odoo localization semantics; protocol identity is based on closed status/phase/activity facts rather than translated phrases.

### Reasoning summaries

Readable provider summaries are separate from both public activity and Assistant prose:

```text
item/reasoning/summaryTextDelta -> bounded reasoning-summary live channel
item/reasoning/textDelta        -> ignored / never projected
```

No private chain-of-thought is exposed. Providers without readable summary support fall back to semantic host activity without changing turn success.

### Typed Odoo references

Current grounded first-class kinds are:

```text
odoo_record
odoo_model
```

Capability results may project bounded already-readable record identities after output-schema validation and effective-user re-read. Before navigation the browser sends only the typed descriptor back to Odoo; Odoo revalidates current model eligibility, existence and read access before returning a form/list navigation descriptor. Revoked or deleted targets fail closed.

Unknown OCA/custom models receive a generic current-schema/access-driven summary using a bounded set of currently readable safe fields. The current implementation intentionally revalidates on every reference resolution instead of caching a provider-generated presentation spec, avoiding stale schema/ACL state and an extra provider dependency in browser navigation.

### Progressive disclosure

Record details default to five rows. `show more` advances in bounded pages. `show remaining` is offered only below the configured hard render ceiling. Over-limit expansion is blocked only at the presentation layer and an Odoo model/list fallback remains available.

## 6. Queue/concurrency/failure invariants

Accepted P5.1-P5.5 behavior remains authoritative:

- per-conversation frontend scopes;
- one active causal turn per conversation;
- cross-conversation concurrency within scheduler capacity;
- bounded two-slot scheduling, fairness and backpressure;
- explicit approval/failure/recovery surfaces;
- one authoritative final Assistant message;
- uncertain post-write outcomes are never blindly retried as effect-safe.

P5.8 presentation failures are best-effort and cannot change business-effect success or authorization.

## 7. Retrieval/RAG and technical operations

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

## 8. Formal roadmap state

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

P5.8 prepared validation chain:

```text
P5.8-DETERMINISTIC-REGRESSION
P5.8-FULL-ADDON-REGRESSION
P5.8-HOOT-ADDON
P5-REAL-SEMANTIC-ACTIVITY
P5-REAL-ACTIVITY-DEDUPE
P5-REAL-REASONING-SUMMARY
P5-REAL-ACTIVITY-I18N
P5-REAL-NAVIGATION-REFS
P5-REAL-BATCH-DISCLOSURE
P5-REAL-ACTIVITY-RECONNECT
```

None of those P5.8 gates is recorded PASS by the implementation-only run. Execute `research/P5.8_VALIDATION_RUNBOOK.md` on exact current `main`; a failed HARD gate remains P5.8 repair work, and only a reviewed green chain makes Phase 6 eligible.
