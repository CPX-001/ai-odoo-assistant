# ADR-021 — Provider-neutral planning, recovery units and short-lived EffectJournal

## Estado

Accepted

## Contexto

ADR-019 established the correct authority boundary: Odoo owns the iterative decision loop and the
provider returns one untrusted decision at a time. It deliberately limited PLAN work to one canonical
stage-only proposal while approval, the write barrier, verification and recovery were being
stabilized.

Phase 6 needs deeper visible planning and bounded multi-step effects without moving authority into
Codex or pretending that every future effect can share one database transaction. It also needs a
small recent-effect record that can distinguish reversible, reconstructable, irreversible and
external/unknown outcomes without becoming an unlimited backup system.

## Decisión

The provider-neutral host loop remains authoritative. ADR-021 supersedes ADR-019 only where ADR-019
fixed the exact three-branch decision set and one canonical PLAN proposal.

The neutral decision contract may additionally carry a `task_plan_update`. A TaskPlan is a bounded,
user-visible progress artifact. It contains no capability arguments, approval or execution authority
and is never a substitute for EffectPlan validation.

Effectful work remains a sequence of typed `CapabilityDefinition` invocations. The host may
accumulate up to the configured hard ceiling of effect steps and prepares them through the existing
`CapabilityPlanService`; no generic script/program body is introduced.

### Recovery units

Every prepared EffectPlan step receives a host-derived recovery mode and recovery-unit identity:

```text
odoo_atomic
  consecutive Odoo-local steps that intentionally share one database transaction/recovery unit

segmented
  an explicitly declared durable internal unit; the host checkpoints completion before a later unit

external
  an external/non-transactional unit; the host durably records intent before execution and treats an
  interrupted in-flight outcome as uncertain
```

Provider text cannot choose or upgrade this authority. Recovery mode comes from trusted capability
metadata plus host defaults and is revalidated before execution.

For every unit the host preflights version, binding, preconditions, policy/approval and dependency
state before crossing that unit's durable execution checkpoint. Between durable units the host
commits the completed unit state. The next unit reacquires the turn effect lock and rechecks current
Stop/redirect state before execution.

An already persisted `executing` recovery unit is never blindly replayed. Internal transactional
units may be classified as rolled back after worker transaction failure; an external in-flight unit
is `uncertain` until a recovery procedure can establish the outcome.

### EffectJournal

Odoo owns a short-TTL EffectJournal keyed to the durable turn and typed plan steps. It stores bounded
minimum before/after/receipt evidence needed for recent recovery and inspection. Current
classification vocabulary is:

```text
reversible
reconstructable
irreversible
external_or_unknown
```

`reversible` is a structural host claim: a compatible HOST-only compensator must exist for the
current capability/version/effect family. `reconstructable` is weaker and must never be presented as
undo/reversion. `irreversible` and `external_or_unknown` must not gain a fake revert action.

The journal is not a backup, audit warehouse or chain-of-thought store. It has bounded payloads,
short retention and scheduled cleanup. Normal browser access receives only a sanitized summary;
raw snapshots remain host-side.

Existing P5.8 compensation remains the implementation for supported safe reversions. When a
verified compensator completes, the matching recent journal rows are marked reverted.

### Provider boundary

All TaskPlan, EffectPlan, recovery-unit, journal, policy, approval, write-barrier and verification
semantics live above provider adapters. Codex remains the current concrete provider and owns only
its App Server transport, Structured Outputs translation, provider events/errors and interactive
steer/interrupt behavior. A future provider implements the same neutral decision port rather than
copying the Odoo agent/recovery logic.

## Consecuencias

- multiple Odoo-local steps can truthfully share one atomic recovery unit;
- future segmented/external capabilities have an explicit durable certainty boundary before they are
  promoted;
- completed durable units and in-flight uncertain units can be distinguished after failure;
- the model still cannot execute, retry or compensate effects directly;
- current safe compensators are reused instead of introducing a second undo framework;
- EffectJournal retention is deliberately finite and does not promise general historical recovery;
- full Phase-6 acceptance remains gated by the accumulated periodic real-environment tests.

## Compatibilidad y rollback

Format-v1/v2 prepared plans remain readable and are conservatively upgraded to host-derived recovery
metadata at execution. Existing single-unit Odoo-local callers retain the old one-barrier behavior.

Rolling back this decision means disabling the Phase-6 recovery/journal overlay and returning the
active product composition to one Odoo-local recovery unit. It must not replay any turn that already
crossed a durable barrier or erase journal evidence needed to resolve an uncertain external effect.

## Referencias

- `ADR-014-unified-host-authorized-agent.md`
- `ADR-017-addon-capability-framework.md`
- `ADR-019-host-owned-iterative-decision-loop.md`
- `../research/P6_PLANNING_EFFECTPLAN_IMPLEMENTATION.md`
- `../research/AGENTIC_PRODUCT_EVOLUTION_PLAYBOOK.md`
