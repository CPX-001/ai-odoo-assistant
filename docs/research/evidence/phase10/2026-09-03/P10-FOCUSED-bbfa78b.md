# P10 focused validation — bbfa78b

Date: 2026-09-03
Status: **PASS / FOCUSED ONLY / REAL GATES PENDING**

## Tested lineage

```text
bbfa78b87d2870fb4b79cbd1854d00f5d1087375
```

The checkout was `main`, clean at the tested commit, on Ubuntu 24.04 under WSL2.
The Odoo gate used Odoo 18.0 and the disposable PostgreSQL database
`odoo_ai_p10_focus_20260903_cdx1`.

## Failure and repair

The first focused run found two repair classes:

- Ruff reported import/order modernization plus intentional broad exception catches
  at security and uncertainty boundaries. Mechanical findings were fixed; the
  intentional catches now carry narrow explanatory `BLE001` suppressions so the
  fail-closed semantics remain explicit.
- The Odoo test expected `odoo.module.inspect.dependencies` to be a tuple, but the
  capability contract preserves JSON arrays as immutable list-compatible values.
  The test now asserts both JSON list identity and mutation denial.

The initial Odoo run selected four methods and failed one assertion. After repair,
all focused gates were rerun on the exact commit above.

## Executed gates

### Static / compile / lint

```text
.venv/bin/python -m compileall -q <P10 runtime, broker and focused test files>
.venv/bin/python -m ruff check <P10 runtime, broker and focused test files>
```

Result: **PASS**. Ruff reported `All checks passed`.

### Dependency-light broker/client

```text
.venv/bin/python -m unittest -v \
  tests.unit.test_phase10_host_broker \
  tests.unit.test_phase10_host_broker_client
```

Result: **PASS — 14 tests**.

### Focused Odoo Technical/host

```text
/odoo/venv/bin/python3 /odoo/odoo-server/odoo-bin \
  --config=/etc/odoo-server.conf \
  --database=odoo_ai_p10_focus_20260903_cdx1 \
  --addons-path=/odoo/odoo-server/addons,/odoo/custom/addons/odoo-ai-assistant/addons \
  --update=odoo_ai_assistant \
  --test-enable \
  --test-tags=/odoo_ai_assistant:TestPhase10HostOperations \
  --stop-after-init
```

Result: **PASS — 4 selected test methods, 0 failures, 0 errors**. This run exercised
real Odoo 18 registry/ORM and PostgreSQL behavior, including Technical versus User
discovery, `su=False`, module inspection, fixed PostgreSQL diagnostics, broker
availability guards and durable EffectPlan binding.

Non-failing reStructuredText warnings emitted while loading dependency metadata did
not originate from or invalidate the selected P10 assertions.

## Remaining gates

No host broker deployment existed on the test host: the policy, socket, durable
ledger and `odoo-ai-host-broker.service` were absent. Therefore none of the following
is represented as executed or PASS:

```text
broker deployment/systemd smoke
P10-REAL-PROFILE-DENIAL
P10-REAL-CONFIG-PATCH
P10-REAL-SERVICE-OPERATION
P10-REAL-POSTGRES-DIAGNOSTIC
P10-REAL-PRIVILEGE-BOUNDARY
```

`P10-REAL-MODULE-UPDATE` remains blocked by the missing lifecycle-safe maintenance
adapter. Phase 10 remains incomplete.
