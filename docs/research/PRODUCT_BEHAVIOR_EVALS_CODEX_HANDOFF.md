# Codex handoff — implement Product Behavior Evals v1 and close pre-live-P7 gate

Date: 2026-08-31  
Owning specification: `PRODUCT_BEHAVIOR_EVALS_V1.md`  
User direction: product-behavior baseline is a gate before further live Phase-7 integration.

## 0. Reconstruct current state first

Work only from the current repository state. Before changing code:

1. pull/read current `main`;
2. read `AGENTS.md`;
3. read `docs/README.md`, `docs/CURRENT_STATE.md`, `docs/CHAT_PRODUCT_FLOW.md`;
4. read `docs/research/EXECUTION_STATE.md` and `P7_MINI_FRAMEWORK_IMPLEMENTATION.md`;
5. read `PRODUCT_BEHAVIOR_EVALS_V1.md` completely;
6. inspect current relevant implementation/tests rather than relying on this handoff's filenames alone.

At the design checkpoint inspected for this handoff, Phase 7 had already begun and the P7.1
`CapabilityProvider` foundation was present but **not wired into the live effective catalog**. Do not roll it back
merely to restore chronological purity. Preserve it, run its already-required focused deterministic gate, and then
pause P7.1 before live-catalog wiring until the product-behavior gate below is green.

If `main` has advanced, reconcile this instruction against the new code and `EXECUTION_STATE.md`; do not overwrite
newer work.

## 1. Objective

Create a permanent eval system that catches failures which ordinary technical tests miss:

```text
technically valid runtime
but
bad user behavior / bad UX / wrong tool strategy / excessive friction / poor latency
```

Implement the v1 scenario catalog as a versioned, machine-readable dataset plus a runner/reporting layer. Keep
hard deterministic assertions separate from probabilistic/graded dimensions.

This is not a request for one giant brittle browser script and not a request to replace pytest/HOOT/Odoo tests.
Reuse existing product test infrastructure where it is already the simplest path.

## 2. Required suites

Implement:

```text
SMOKE: 12–15 scenarios, 1 trial
FULL: 50+ scenarios, 3 trials for probabilistic agent behavior
```

The specification defines the initial 54-case catalog and recommended SMOKE subset.

The harness may use YAML, JSON or Python fixtures after inspecting the repository. Prefer a human-editable dataset
with stable IDs and a runner that can select by scenario/category/language/persona.

Do not encode exact hidden tool sequences unless the product explicitly requires one semantic capability. Prefer
observable constraints such as no writes, grounded live read, no approval, maximum call range, or use of the
sale-order semantic action instead of a state patch.

## 3. Persona/fixture strategy

Create disposable deterministic fixtures for:

- normal internal business user;
- limited internal user with real access restrictions/record rules;
- admin for settings/runtime cases.

Do not run the whole suite as admin.

For limited-user cases, use real Odoo ACL/record-rule behavior. Expected UX is not simply `not found`:

- inaccessible single target -> explain permission limitation without leaking hidden data;
- mixed visible/invisible collection -> return visible subset and explain that some matching data could not be
  included because of access restrictions.

Inspect actual Odoo 18 groups/modules in the test environment before choosing fixture group XML IDs. Avoid a
synthetic permission mechanism that bypasses Odoo's actual security stack.

## 4. Implement timing/observability needed by the evals

The eval report must separate provider latency from Odoo/tool latency. Add the minimum safe telemetry necessary to
capture at least:

```text
submit -> durable turn
queue wait
provider decision durations
per-capability execution durations
preview duration
verification duration
first meaningful public activity
first answer delta
final answer
```

For each capability timing store only safe metadata such as stable capability id/class, elapsed time and sanitized
outcome code. Do not log raw sensitive arguments/results merely for evals.

The Atlas recommends correlation/timing metadata and warns against turning tracing into a second secret store.
Follow that pattern.

A tool taking ~30 seconds must be visible as a tool anomaly instead of being hidden inside one aggregate turn time.
Do not set arbitrary hard thresholds before the first real baseline unless an existing accepted contract already
provides one. Record distributions and obvious outliers first, then freeze thresholds from evidence.

## 5. Streaming regression — investigate and repair with evidence

The user reports that the chat often stays on thinking and then receives the complete answer at once.

Current architecture already intends real provisional answer streaming:

```text
item/agentMessage/delta
 -> StructuredFinalAnswerDeltaExtractor
 -> answer.delta
 -> persisted Odoo live event
 -> browser live polling
 -> streamingText
 -> authoritative final reconciliation
```

Inspect at minimum:

```text
runtime/agent/answer_stream.py
runtime/agent/codex_streaming.py
models/live event persistence / emit path
controllers live/status routes
assistant_live_stream_client.js
assistant_panel_streaming_service.js
current OWL message/activity projection
P4 tests/gates and later regression evidence
```

Known observations from the inspected checkpoint:

- the structured extractor buffers until the final-answer JSON branch and withholds an open-string increment under
  64 characters;
- browser polling cadence is 500 ms;
- the old real P4 first-delta gate passed on the Phase-4 checkpoint;
- the final Phase-6 periodic run did not re-execute the real first-delta gate; its basic-chat smoke did not prove
  useful provisional text.

Instrument these points before guessing:

```text
provider_first_agent_message_delta
extractor_first_answer_chunk
live_event_first_answer_commit
browser_first_answer_delta
browser_final
```

Required outcome:

- long direct answer visibly streams before completion;
- long grounded Odoo synthesis visibly streams before completion;
- final parity remains exact;
- cancellation/redirect semantics remain safe;
- no fake streaming made by chunking a final answer after completion.

If the provider/Structured Output shape itself prevents useful streaming, redesign only the provider/presentation
seam needed to obtain real provisional text while retaining final `NextDecision` validation as authority. Do not
weaken host authority to improve animation.

## 6. Plan UX — required behavior change

Current inspected implementation stores `planning_mode` as a per-user preference and the `+` menu remains active
until toggled. That conflicts with the user-approved product contract.

Implement Plan as a **one-shot next-turn composer option**:

```text
select Plan
 -> show removable Plan chip/tag inside composer/input area
 -> submit next turn with deliberate planning captured in that turn's immutable settings
 -> remove Plan chip after successful submission
 -> next turn is Direct unless selected again
```

Requirements:

- Direct remains default and never shows TaskPlan;
- selecting Plan for a trivial/social prompt must not generate a pointless one-step TaskPlan;
- legacy stored `auto`/deliberate data remains migration-readable but must not silently keep Plan active;
- no authority/policy/approval semantics change;
- update frontend, snapshot/input path and tests coherently rather than adding an independent second planning mode.

Choose the smallest architecture consistent with existing turn settings. If a per-user DB field becomes legacy-only,
retain or migrate it safely rather than deleting it blindly.

## 7. General answers vs live Odoo facts

Freeze these semantics in tests/prompt/context behavior:

```text
general fact independent of DB
 -> direct model answer allowed, zero Odoo tools preferred

fact about this installation
 -> authoritative local evidence required
```

Do not reintroduce a rigid GENERAL/QUERY/HOW_TO/ACTION router. The provider can select tools agentically; the host/
eval contract simply forbids ungrounded installation claims.

## 8. Repeated-fact/cache investigation

Do not add a generic fact cache as an automatic part of this slice.

Inspect the existing P5.6 `ConversationContextManager` and measure repeated same-chat questions. It currently carries
recent messages, deterministic rolling summaries and refs, so it may reduce reasoning overhead, but a previous
Assistant sentence is not freshness-aware authority.

For the v1 repeated-fact scenario:

1. ask a live fact;
2. ask it again in the same conversation and record provider/tool timings;
3. mutate the underlying fixture;
4. ask again and require the new value.

If the second turn is already acceptably fast, document that no cache is justified now. If not, leave a measured
follow-up for the Evidence/Freshness layer unless a small Odoo-native optimization can prove safe.

Any future cache that permits skipping a live read must bind security scope, company scope, query identity,
provenance and freshness/invalidation. Do not use RAG or conversation summary as authoritative cache of mutable
business records.

## 9. Semantic activity expectations

Normal mode should describe the business work, not tools.

For example:

```text
Consultando presupuestos de Eval Acme
Evaluando presupuestos de Eval Acme respecto al límite de 1.000 €
Filtrando los presupuestos que superan 1.000 €
```

Do not expose raw capability ids/args to normal users. Diagnostic detail may show capability identity and timing but
still excludes private reasoning/secrets.

Freeze visual causal order:

```text
user message
TaskPlan if applicable
semantic reasoning/activity
approval if required
settled activity/reasoning block
final answer
references / receipt / reversion controls
```

The final settled `Ha pensado...` block belongs **above** its answer, never below it.

Zero-tool direct answers should not leave a fake reasoning-history artifact.

## 10. Approval and write behavior

Implement/evaluate the product contract from the specification:

- reads never ask approval, including Strict;
- freeze current four autonomy semantics at product level;
- delete always requires approval even with Full access;
- one coherent multi-step/batch request should normally have one approval boundary, not repeated prompts per step;
- approval must rebind/reappear only when material plan/risk/precondition changes justify it;
- batch preview: summary + first 5 rows + progressive disclosure;
- semantic business capability wins over generic CRUD when available (`sale_order.confirm` is the canonical current
  example);
- synthetic/demo data only when explicitly requested/authorized.

## 11. Create/default semantics

Do not populate optional fields merely because defaults exist.

Correct interpretation:

- optional fields not requested -> omit them;
- omission allows normal ORM/server defaults to apply naturally;
- required field with safe ordinary default may use/allow that default if it does not materially change intent;
- material required choice with no safe default -> ask;
- ask multiple related missing values in one consolidated question where possible.

Add eval fixtures proving that contact creation does not invent email/phone or force optional fields.

## 12. Partial success and customer-facing failures

Normal UI must sound like a product, not a traceback viewer.

For partial success, include:

- successful count/items;
- failed count/items;
- safe reason when known;
- whether user action is required and what action;
- safe continuation/retry option;
- no duplicate retry of already verified effects.

Keep diagnostic code/timing available only in detailed/diagnostic evidence.

## 13. Navigation/context

Preserve the current typed-reference authority model.

Current-screen `este/esto/aquí` should resolve directly when context is unambiguous; still revalidate before effect or
navigation. `¿Dónde está X aquí?` should return a real host-resolved Odoo reference rather than prose plus an invented
route.

Do not add source/module HOW_TO evals to v1 because the user explicitly deferred tests for not-yet-implemented
technical/source diagnosis. However, preserve the future product requirement in documentation: after the Phase-8
source/XML/module layer exists, installed third-party/custom addons must be autodiscoverable for questions such as
`¿el módulo X permite hacer Y?` and `¿cómo lo uso?`.

## 14. Language and viewport

V1:

```text
Spanish ~60%
Catalan ~20%
English ~20%
desktop only
```

Include language-switching behavior. Do not duplicate all 54 cases across languages and do not add mobile work in
this slice.

## 15. Grading

For each trial produce:

```text
HARD assertions
quality score
structured metrics
sanitized observations
```

Do not use one LLM judge as the only truth. Use deterministic graders wherever possible:

- DB final state;
- number/type of writes;
- approvals;
- TaskPlan visibility;
- capability availability/calls;
- references;
- ACL outcome;
- live event/order;
- streaming timings/parity.

Use model/judge grading only for genuinely semantic dimensions such as clarity/relevance, and keep it secondary to
hard state assertions.

## 16. Validation order

Because the P7.1 foundation is already landed but local validation is pending:

1. run only the existing focused P7.1 provider-extension deterministic gate and static checks required by its current
   record;
2. do **not** continue live provider-catalog wiring;
3. implement eval dataset/harness + focused deterministic harness tests;
4. implement/fix product gaps required for v1, especially Plan one-shot and real streaming if reproduced;
5. run focused affected tests;
6. execute real SMOKE on disposable Odoo data;
7. repair every HARD failure;
8. execute FULL with 3 trials for probabilistic cases;
9. publish sanitized baseline evidence and thresholds;
10. update `EXECUTION_STATE.md`, current docs and this record;
11. resume P7.1 live effective-catalog work only after the gate is green.

Do not run unrelated full regression suites unless a current runbook/state explicitly authorizes them. The FULL
**product eval** defined here is its own required gate; it does not implicitly authorize every repository regression.

## 17. Expected repository output

Adapt names if existing structure suggests a better fit, but the finished slice should contain equivalents of:

```text
versioned product-eval dataset
runner/selectors for smoke/full/scenario/language/persona
fixture setup/cleanup helpers
hard graders
quality grader seam
safe timing collector/report
streaming-specific real gate(s)
Plan one-shot UI/runtime tests
sanitized baseline evidence
updated runbook/state/docs
```

Do not present a dataset file alone as completion. The real product path must actually execute the gate before it is
marked PASS.

## 18. Final review

Before publishing:

- inspect the diff for obsolete planning UX/persistence assumptions;
- ensure no hidden/private reasoning is captured for grading;
- confirm no secrets/customer data are written into evidence;
- verify the harness itself cannot execute unsafe arbitrary tools/ORM merely for testing convenience;
- verify fixture cleanup is explicit;
- update docs that still claim P6 validation is pending;
- keep Git/main coherent and do not describe unexecuted real tests as green.
