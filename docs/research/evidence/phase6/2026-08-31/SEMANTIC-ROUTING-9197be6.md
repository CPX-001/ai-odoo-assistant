# Focused semantic-routing checkpoint

Date: 2026-08-31  
Implementation commit: `9197be6659f7397ed577ec41d813764dcd5ca998`  
Base pulled before implementation: `d6c41b12b7afc46be10d02b25cf50574399fa965`  
Result: focused contracts PASS; real semantic behavior PASS; short-turn latency remains open

## Scope

This checkpoint validates only the repaired short-turn/TaskPlan contract. It is not a Phase-6
acceptance run and does not turn any unexecuted periodic HARD gate into PASS.

Expected behavior:

- direct questions may finish as one model answer with no generic Thought and no TaskPlan;
- a short Odoo lookup may perform the minimum bounded reads without a TaskPlan;
- adaptive TaskPlan is unavailable until the host has evidence of genuinely multi-phase work;
- the host owns the exact TaskPlan revision/kind schema;
- normal/compact failure history does not render every provider retry beside the terminal failure.

## Focused deterministic validation

```text
python -m unittest \
  tests.e2e.test_host_loop_contract \
  tests.e2e.test_phase6_adaptive_planning_contract

18 tests, PASS

python -m pytest -q tests/unit/test_codex_provider_conformance.py

8 tests, PASS
```

Focused Odoo 18 runs in a disposable UTF-8 PostgreSQL database:

```text
TestCodexDecisionAdapter plus
TestEmbeddedAgentRuntime.test_aggregate_count_contract_is_explicit_for_the_model

9 methods selected / 13 Odoo test cases counted, 0 failures, 0 errors

TestCanonicalPlanHostLoop

6 methods / 8 Odoo test cases counted, 0 failures, 0 errors
```

Focused HOOT coverage for terminal provider-failure collapse:

```text
1 test, 3 assertions, PASS
```

The HOOT check ran after the frontend change. Later edits before `9197be6` were backend/tests/docs
only and did not change the tested frontend files.

No full dependency-light, addon, HOOT or repository regression was run; repository policy did not
authorize one for this focused repair.

## Real Odoo + Codex smoke

Environment:

```text
Odoo: 18.0 Community
database: disposable, no demo sales data
provider: Codex App Server, codex-cli 0.144.2
model: provider default gpt-5.6-sol, default low reasoning effort
user: internal administrator; business capabilities still execute with su=False
```

Observed:

1. `¿Qué capacidades tienes?`
   - completed successfully;
   - `task_plan = null`;
   - public durable events were only `queued`, `started`, `completed`;
   - no `reasoning.started`/Thought and no capability call;
   - wall time: 14.75 seconds.
2. `¿Cuántos presupuestos hay actualmente?`
   - completed with the correct disposable result: 0 draft/sent quotations;
   - `task_plan = null`;
   - exactly one effective-schema read and one aggregate read;
   - count contract used the required null field and produced no correction loop;
   - wall time: 30.55 seconds.

The behavioral regression is fixed: technical schema/query calls no longer manufacture a public
TaskPlan, and the former invalid aggregate argument/revision loop is absent. The timings are still
too high for the intended near-immediate short-turn experience. They are recorded as performance
debt rather than described as PASS.

The disposable Odoo server, database and PostgreSQL cluster were stopped and removed after the run.
