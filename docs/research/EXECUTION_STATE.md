# Stabilization execution state

State format: 49
Updated: 2026-08-31

Accepted lineage:

```text
P0-P4 through 8a4432dc9852eacc422b8c794b6613c75da702a9
P5.1 through f7f924ce944db86e896745fef83ea2fb6fd6583a
P5.2 through b4fbb034e113a41c26db77cb274f2b3b30f6eee3
P5.3 through 32e836e7789ea72f3ba0d32fe6bdabbb092f5953
P5.4 through 3e2b38d68fe172cd2cf92d7794159f73476ac23d
P5.5 through 8427c8849b1e1f3afa6337de1209a6027410c266
P5.6 through 720102f2a13af5240c779b07cc71ee65994a87b1
P5.7 through 074a71c29a6a6109ae7412e7b1f9850c4449e379
P5.8 through 688f569d441a40a4637ad6a23f111e584e18c955
P6 final acceptance through 0b1bcab39b71dfbe02526cda7cf7ac8e218ac4b0
```

P6 is **COMPLETE**. Phase 7 has started, but live Phase-7 integration is intentionally paused behind the
user-directed Product Behavior Evals v1 gate.

The pre-real Product Behavior implementation checkpoint is now present on `main`: the v1 catalog/harness, one-shot
Plan path and additional timing/streaming observability have been implemented. They are **not yet accepted** because
the focused deterministic/Odoo/HOOT validation and the real SMOKE/FULL product runs have not been executed at this
checkpoint.

## Current cursor

```text
phase: 7
phase_name: mini-framework, feature negotiation and Assistant self-awareness
phase_state: IN_PROGRESS_PAUSED_BEFORE_LIVE_INTEGRATION
active_phase_record: docs/research/AGENTIC_PRODUCT_EVOLUTION_PLAYBOOK.md
active_slice: PRE-P7-LIVE-product-behavior-baseline-v1
active_slice_record: docs/research/PRODUCT_BEHAVIOR_EVALS_V1_IMPLEMENTATION.md
active_slice_state: LOCAL_VALIDATION_REQUIRED
current_gate_type: PRODUCT_BEHAVIOR_FOCUSED_VALIDATION
blocking_work: do not wire the P7.1 provider extension boundary into the live effective capability catalog and do not start P7.2
blocking_validation: run the focused dependency-light/static, Odoo settings-snapshot and HOOT gates recorded in PRODUCT_BEHAVIOR_EVALS_V1_IMPLEMENTATION.md; after PASS execute real SMOKE then FULL
pending_periodic_validation: none; the product-eval FULL is a dedicated gate and does not authorize unrelated repository-wide regression
periodic_regression_runbook: docs/research/PERIODIC_FULL_REGRESSION_RUNBOOK.md
latest_accepted_evidence: docs/research/evidence/regression/2026-08-31/FULL-REGRESSION-fc022a6.md
latest_executed_evidence: docs/research/evidence/phase7/2026-08-31/P7.1-FOUNDATION-3c9e118.md
latest_implementation_checkpoint: docs/research/PRODUCT_BEHAVIOR_EVALS_V1_IMPLEMENTATION.md
implementation_checkpoint_sha: 5d9c47ab70a01bf88f3b04d86056b6ffff501a36
next_action: execute only the focused validation gate from PRODUCT_BEHAVIOR_EVALS_V1_IMPLEMENTATION.md; if green, build/use disposable real-Odoo scenario executors and run the 15-case real SMOKE before FULL
```

## Phase summary

```text
P0 COMPLETE
P1 COMPLETE
P2 COMPLETE
P3 COMPLETE
P4 COMPLETE
P5 COMPLETE
P6 COMPLETE
  P6.1 TaskPlan vs EffectPlan        VALIDATED_PART1
  P6.2 direct/deliberate/replan      VALIDATED_PART1
  P6.3 multi-step EffectPlan         VALIDATED_PART1
  P6.4 atomic vs segmented effects   VALIDATED_PART2
  P6.5 separate budgets              VALIDATED_PART1
  P6.6 EffectJournal                 VALIDATED_PART2
P7 IN_PROGRESS / LIVE INTEGRATION PAUSED
  PRE-P7 Product Behavior Evals v1   IMPLEMENTED / LOCAL_VALIDATION_REQUIRED
  P7.1 CapabilityProvider API        FOUNDATION_FOCUSED_VALIDATED
       live effective-catalog wiring BLOCKED_BY_PRODUCT_BEHAVIOR_GATE
  P7.2 Skill/Bundle                  NOT_STARTED
  P7.3 ContextProvider               NOT_STARTED
  P7.4 ProviderProfile               NOT_STARTED
  P7.5 EffectiveAssistantManifest    NOT_STARTED
  P7.6 Technical profile skeleton    NOT_STARTED
  P7.7 Progressive disclosure        NOT_STARTED
P8+ NOT_ELIGIBLE
```

## Phase-6 acceptance checkpoint

The final current-product regression published by `0b1bcab39b71dfbe02526cda7cf7ac8e218ac4b0` closed Phase 6.
Accepted evidence:

```text
docs/research/evidence/regression/2026-08-31/FULL-REGRESSION-fc022a6.md
```

It passed the complete then-current dependency-light/static, Odoo addon and HOOT suites plus all six Phase-6 real
gates. There is no remaining Phase-6 technical gate.

## P7.1 foundation already landed

Starting from accepted `0b1bcab`, the isolated provider-extension foundation described in
`docs/research/P7_MINI_FRAMEWORK_IMPLEMENTATION.md` was committed before the product-eval design discussion closed.
It currently provides:

```text
CapabilityProvider
CapabilityProviderStatus
discover_odoo_capability_providers(env)
compose_capability_registry(...)
discover_capabilities_for_env(env)
provider provenance on CapabilityRegistry/catalog
optional-provider failure isolation
provider/capability identity conflict rejection
```

The Odoo-registry marker is `_odoo_ai_capability_provider` on trusted installed model code. Discovery is constrained
to the active Odoo registry; it does not scan arbitrary host packages/filesystem.

Crucially, this foundation has **not** yet been wired into live turn execution. Keep it. Its focused gate passed at
the published checkpoint recorded in `docs/research/evidence/phase7/2026-08-31/P7.1-FOUNDATION-3c9e118.md`:

```text
tests/unit/test_capability_provider_extensions.py
```

Result: **8 passed**, plus focused `py_compile`, Ruff and `git diff --check` PASS.

## Product Behavior Evals v1 gate

The user approved a permanent separate eval layer because technical tests can remain green while real behavior
regresses.

Authoritative design/handoff and current implementation checkpoint:

```text
docs/research/PRODUCT_BEHAVIOR_EVALS_V1.md
docs/research/PRODUCT_BEHAVIOR_EVALS_CODEX_HANDOFF.md
docs/research/PRODUCT_BEHAVIOR_EVALS_V1_IMPLEMENTATION.md
```

Required direction remains:

```text
SMOKE: 12-15 scenarios, one probabilistic trial
FULL: 50+ scenarios, three probabilistic trials
hard deterministic graders + semantic quality scoring
real Odoo users/ACLs + real provider path
per-provider and per-capability timing
streaming timing/parity
sanitized evidence
```

HARD product invariants include no unauthorized writes, no read approvals, no TaskPlan in Direct, no stale effect
after correction/Stop, no ungrounded current-installation facts, no raw private reasoning/secrets, no duplicate final
answer/effect, safe ACL behavior and host-resolved navigation.

### Implementation checkpoint now landed

The pre-real implementation through `5d9c47ab70a01bf88f3b04d86056b6ffff501a36` adds the coherent boundary that can
be validated before spending real-provider/browser time:

```text
one-shot Plan composer option + removable chip
planning_mode carried by the submitted turn and captured immutably
legacy stored deliberate/auto prevented from silently activating new turns
Plan consumption at durable turn persistence
54 stable Product Behavior scenarios
15-case SMOKE subset
suite/id/family/language/persona selectors
SMOKE x1 / FULL x3 trial policy
HARD grading + secondary quality-grader seam
safe timing/reporting + guaranteed cleanup boundary
provider-decision timing diagnostics
provider-first-delta / extractor-first-chunk streaming diagnostics
```

This implementation checkpoint is not evidence that the new path passes. The next required action is exactly the
focused validation recorded in `PRODUCT_BEHAVIOR_EVALS_V1_IMPLEMENTATION.md`; no real SMOKE/FULL result is claimed.

### Product behavior changes/findings carried by the gate

1. **Plan is one-shot.** The implementation now treats Plan as next-turn composer state rather than a persistent user
   mode. It must still pass the focused frontend/Odoo snapshot tests and the later real product scenarios. A trivial or
   social prompt with Plan selected must not manufacture a useless TaskPlan.
2. **Answer streaming must be revalidated.** The user reported that the chat often remains thinking and then displays
   the whole answer at once. Historical Phase-4 streaming PASS does not disprove a later regression. The implementation
   now adds safe first-provider-delta and first-extractor-chunk diagnostics; the real SMOKE must locate and repair any
   remaining provider -> extractor -> Odoo live event -> browser bottleneck.
3. **Tool timing is first-class.** Eval output must expose capability duration separately from provider-decision
   latency so a single anomalous local tool cannot hide inside aggregate turn time. The harness can derive
   tool/preview/verify durations from existing activity ids/timestamps and consumes sanitized provider duration
   diagnostics.
4. **Installation facts require evidence.** Current conversation summary can preserve continuity but is not a
   freshness-aware authoritative business-data cache. Measure repeated-query latency first; do not add unsafe cache
   semantics merely for speed.
5. **General knowledge stays cheap.** A DB-independent question may answer with zero Odoo tools; future RAG must not
   impose retrieval on every turn.
6. **Semantic activity is business-facing.** Normal users see meaningful work such as consulting/filtering a customer
   quotation set, not raw capability names/arguments. Settled activity belongs above its final answer.
7. **Create defaults are conservative.** Do not fill optional fields merely because defaults exist; omit unrelated
   optional fields and let Odoo defaults apply naturally when omitted.

## Focused validation now blocking

Run only the focused gate defined in `docs/research/PRODUCT_BEHAVIOR_EVALS_V1_IMPLEMENTATION.md`:

```text
dependency-light Product Behavior harness/provider timing + direct planning/answer-stream regressions
focused py_compile + Ruff + git diff --check
Odoo TestAssistantTurnSettingsSnapshot
focused HOOT:
  assistant_planning_service.test.js
  assistant_plan_one_shot_submit.test.js
  assistant_live_stream_client.test.js
```

Do not broaden this into an unrelated full repository regression. If this focused gate passes, continue inside the
same pre-P7 slice with disposable real-Odoo fixture executors and the 15-case real SMOKE. Repair every unresolved
HARD failure before FULL.

## Current streaming evidence boundary

`docs/research/PHASE4_ANSWER_STREAMING.md` remains valid historical acceptance for its checkpoint. Current code still
contains the provisional `answer.delta` path, but the Phase-6 final periodic regression did not rerun the real
`P4-REAL-FIRST-DELTA` gate. Its basic-chat smoke checked terminal behavior rather than useful provisional answer
arrival. The product gate must establish current evidence instead of assuming streaming remains healthy.

The current implementation adds sanitized milestone diagnostics without treating provisional text as authority:

```text
provider first agent-message delta
structured extractor first answer chunk
existing live-event commit/browser first delta/final timing path
```

No raw provisional answer text or private reasoning is stored merely for diagnostics.

## Conversation context/cache finding

P5.6 `ConversationContextManager` currently stores bounded recent messages, deterministic rolling summaries, active
refs and verified-effect refs. It can support follow-up continuity and may reduce reasoning overhead. However:

```text
previous Assistant prose != freshness-aware live business evidence
```

The general `evidence_refs` slot still awaits the later Evidence layer. A future fact cache may skip live reads only
with security scope, company scope, query identity, provenance and freshness/invalidation binding. Prefer to decide
that from measurements and Phase-8 Evidence/Freshness work rather than prematurely introducing a second truth store.

## Future installed-module HOW_TO requirement

Do not add source/module diagnosis cases to v1 while the source/XML intelligence layer is not implemented. Preserve
the target requirement for Phase 8: the Assistant should eventually autodetect installed third-party/custom modules
and answer questions such as whether module X supports a function and how to use it by inspecting current
module/runtime/source/XML evidence, not by hard-coded module knowledge.

## Provider boundary

Codex remains the concrete configured provider, but host planning/effect/ACL/policy/recovery authority stays
provider-neutral:

```text
Odoo host
 -> PlanningDecisionEngine
 -> NextDecisionEngine provider port
 -> Codex adapter today / other adapters later
```

P7 capability providers may contribute definitions after the gate, but cannot grant themselves execution authority.

## Invariants carried forward

- Odoo remains persistence and operational authority.
- Business operations execute under the effective user with `su=False`.
- `CapabilityDefinition` remains atomic executable authority.
- Planning strategy and TaskPlan never grant effect authority.
- Direct mode never exposes a TaskPlan.
- No arbitrary SQL/Python/shell/sudo/unrestricted ORM is exposed.
- Policy/approval/preconditions/write-barrier/verification remain host-owned.
- Recovery-unit mode/classification is host-derived.
- Persisted in-flight effects are never blindly retried.
- Stop/redirect cannot bypass the effect boundary.
- Raw/private provider reasoning never becomes TaskPlan/activity/eval evidence.
- Provider-specific adapters remain below the neutral decision contract.
- Broad/real validation is executed only when explicitly required by the active gate/runbook.
- No GitHub Actions are used while repository policy says usable runners are unavailable.

## Exact stop rule

Do not continue P7.1 live effective-catalog wiring and do not start P7.2 until:

```text
P7.1 isolated provider-extension focused deterministic gate PASS
AND Product Behavior Evals v1 harness/dataset implemented
AND focused validation of the current Product Behavior implementation PASS
AND real SMOKE executed with zero unresolved HARD failures
AND real FULL baseline executed as specified
AND user-approved Plan/streaming behavior gaps discovered by the gate are repaired or explicitly reclassified by user
```

The harness/dataset implementation condition is now satisfied at the implementation level but is not accepted until
its focused validation passes. After the complete Product Behavior gate is green, return to
`P7_MINI_FRAMEWORK_IMPLEMENTATION.md` and resume P7.1 live integration before P7.2.
