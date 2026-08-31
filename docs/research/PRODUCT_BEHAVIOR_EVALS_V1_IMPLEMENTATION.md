# Product Behavior Evals v1 — implementation checkpoint

Date: 2026-08-31  
Owning spec: `docs/research/PRODUCT_BEHAVIOR_EVALS_V1.md`  
Handoff: `docs/research/PRODUCT_BEHAVIOR_EVALS_CODEX_HANDOFF.md`  
State: `LOCAL_VALIDATION_REQUIRED`

## Scope completed before the next gate

This checkpoint intentionally groups the product changes and permanent eval infrastructure that can
be validated together before spending real-provider/browser time. It does **not** resume live P7.1
provider-catalog wiring.

Implemented in one coherent pre-real slice:

```text
one-shot Plan composer UX
 -> removable Plan chip
 -> planning_mode travels with the submitted turn
 -> immutable turn settings capture deliberate/adaptive
 -> stored legacy deliberate/auto no longer silently activates a new turn
 -> Plan is consumed when Odoo durably accepts the turn
 -> failed pre-persistence submit keeps Plan selected

Product Behavior Evals v1
 -> 54 stable scenarios
 -> recommended 15-case SMOKE subset
 -> selectors by suite / id / family / language / persona
 -> 1 SMOKE trial / 3 FULL trials default
 -> deterministic HARD grader
 -> quality-grader seam without a frozen threshold
 -> guaranteed fixture cleanup boundary through ScenarioExecutor
 -> sanitized report payload

Timing/streaming observability
 -> provider-decision duration emitted as diagnostic metadata only
 -> tool/preview/verify/reasoning duration derivable by paired activity ids
 -> first provider agent-message delta diagnostic
 -> first structured answer-chunk diagnostic
 -> existing browser submit/durable/activity/answer/final timing seam retained
```

The eval harness records neither raw tool arguments/results nor private provider reasoning.
`CapabilityDefinition`, ACL/policy, approval, execution, verification and recovery authority are
unchanged.

## Important behavior repair: Plan consumption point

The one-shot Plan state is consumed at `turn_persisted`, not after the final answer. This matters when
a turn is durably accepted but the browser stream later disconnects: the same Plan must not be
silently reused for another turn.

A compatibility wrapper still resets Plan after a successful non-streaming submit path, but it never
resurrects state that the authoritative streaming submission already consumed.

## Timing contract

Provider decision timings are emitted as:

```text
diagnostic.provider.decision
  duration_ms
  outcome = completed | failed
```

Streaming diagnostics emit only character counts at the first relevant milestone:

```text
diagnostic.streaming.provider_delta
diagnostic.streaming.answer_chunk
```

They are diagnostic historical events, not normal semantic activity, and contain no provisional
answer text. Capability/preview/verification timings continue to use existing activity ids and event
timestamps; the v1 harness pairs them rather than adding another tracing store.

## Permanent eval files

```text
tests/product_behavior/v1/scenarios.py
tests/product_behavior/v1/selectors.py
tests/product_behavior/v1/harness.py
tests/product_behavior/v1/runner.py
tests/unit/test_product_behavior_eval_harness.py
tests/unit/test_provider_decision_timing.py
```

The generic runner deliberately depends on a `ScenarioExecutor` boundary. The next real-product step
must implement/use Odoo/browser fixture executors on disposable data; the generic harness is not
allowed to gain arbitrary ORM/tool authority merely for convenience.

## Focused validation gate now required

Do not run the unrelated full repository regression. Validate only the changed product/eval boundary
and direct regressions.

Dependency-light/static:

```bash
.venv/bin/python -m pytest -q \
  tests/unit/test_product_behavior_eval_harness.py \
  tests/unit/test_provider_decision_timing.py \
  tests/e2e/test_phase6_adaptive_planning_contract.py \
  tests/unit/test_answer_stream_contract.py

.venv/bin/python -m py_compile \
  addons/odoo_ai_assistant/models/turn_planning_one_shot.py \
  addons/odoo_ai_assistant/models/turn_settings_snapshot.py \
  addons/odoo_ai_assistant/runtime/agent/planning.py \
  addons/odoo_ai_assistant/runtime/agent/codex_streaming.py \
  tests/product_behavior/v1/scenarios.py \
  tests/product_behavior/v1/selectors.py \
  tests/product_behavior/v1/harness.py \
  tests/product_behavior/v1/runner.py \
  tests/unit/test_product_behavior_eval_harness.py \
  tests/unit/test_provider_decision_timing.py

.venv/bin/ruff check \
  addons/odoo_ai_assistant/models/turn_planning_one_shot.py \
  addons/odoo_ai_assistant/models/turn_settings_snapshot.py \
  addons/odoo_ai_assistant/runtime/agent/planning.py \
  addons/odoo_ai_assistant/runtime/agent/codex_streaming.py \
  tests/product_behavior/v1 \
  tests/unit/test_product_behavior_eval_harness.py \
  tests/unit/test_provider_decision_timing.py

git diff --check
```

Odoo focused contract:

```text
TestAssistantTurnSettingsSnapshot
```

It must prove explicit deliberate capture, next-turn adaptive fallback, immutable snapshots and
legacy stored planning data not reactivating Plan.

HOOT focused files:

```text
assistant_planning_service.test.js
assistant_plan_one_shot_submit.test.js
assistant_live_stream_client.test.js
```

Use the repository's accepted Odoo `/web/tests` addon filtering mechanism; do not broaden this into a
complete HOOT regression merely because these focused tests are being run.

## Next action after focused PASS

Continue inside the same `PRE-P7-LIVE-product-behavior-baseline-v1` slice:

1. add/use disposable real Odoo fixture executors for the SMOKE scenarios;
2. execute the 15-case SMOKE once through the real configured provider, with browser paths for
   streaming/turn-control/multichat cases;
3. repair every HARD failure, especially any reproduced first-delta regression;
4. only then execute FULL (54 cases, three trials where specified), publish sanitized baseline
   evidence and freeze evidence-backed thresholds;
5. resume P7.1 live effective-catalog wiring only after that product gate is green.

No real SMOKE/FULL result is claimed by this checkpoint.
