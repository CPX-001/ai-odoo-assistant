# P1.3 real provider validation — `49bdac1`

Date: 2026-08-27
Implementation/test SHA: `49bdac1f732acaaee3154ed60baffd675130991a`
Validation IDs: `P1-REAL-VERSION`, `P1-REAL-SOAK-100`
Gate: `HARD`
Result: **PASS**

## Environment

```text
Odoo: 18.0 Community
Codex CLI / App Server: 0.149.1
database: installed local validation database, explicitly updated at the tested SHA
Assistant user: dedicated internal fixture user, effective-user product path, su=false
runtime account state before soak: authenticated
```

The installed Odoo service was stopped, the addon was explicitly updated from the exact checkout,
and the service was restarted before live validation. Startup, HTTP availability, provider
initialize, thread creation and turn completion then ran through the normal persisted-turn and cron
worker product path.

## Odoo regression battery

The selected queue, embedded runtime, host loop, convergence, canonical PLAN, Codex adapter,
capability framework, action and action-revalidation tests were executed against the updated
installed database:

```text
46 test methods
0 failed
0 errors
process exit: 0
```

## P1-REAL-VERSION

The exact supported pair used for the gate was Odoo 18.0 Community and Codex 0.149.1. The provider
account under Odoo's configured `data_dir` reported `authenticated`. All 100 soak members created a
provider subprocess, initialized the App Server, created an isolated ephemeral thread and completed
the bound turn. All 20 read members crossed at least one `tool.started` and `tool.completed` public
boundary through the host-owned capability path.

Result: **PASS**.

## P1-REAL-SOAK-100

The soak used 80 isolated trivial greetings and 20 isolated simple reads against one disposable
partner. It retained only redacted state/event/diagnostic/timing traces outside Git and produced
this aggregate:

```text
total_turns: 100
completion_count: 100
expectation_failures: 0
greeting_turns: 80
read_turns: 20
read_tool_boundary_failures: 0
protocol_shape_failures: 0
provider_process_failures: 0
runtime_unavailable_retries: 0
unknown_notification_diagnostics: 0
host_authority_bypasses: 0
wrong_turn_call_bindings: 0
latency_median_ms: 7818.479
latency_p95_ms: 34563.910
diagnostic_counts: field_not_in_schema=6
```

The six `field_not_in_schema` diagnostics were bounded host corrections during otherwise successful
read turns. They were neither provider protocol failures nor process retries; all affected turns
completed normally.

The required pass criteria were satisfied:

```text
protocol-shape failures = 0
host-authority bypasses = 0
wrong-turn/call binding = 0
```

Result: **PASS**.

## Cleanup and service health

After aggregation, the disposable records were removed:

```text
deleted turns: 100
deleted conversations: 100
remaining fixture users: 0
remaining fixture partners: 0
remaining fixture turns: 0
remaining fixture conversations: 0
```

The temporary runner, per-turn traces, summary and Odoo test log were removed after the sanitized
evidence was recorded. The installed Odoo service was restarted, remained active and returned HTTP
200. No credential, raw prompt, provider output, unrestricted capability payload, business answer
or private reasoning is stored in this evidence.

## Conclusion

`P1-REAL-VERSION` and `P1-REAL-SOAK-100` are closed for
`49bdac1f732acaaee3154ed60baffd675130991a`. This closes P1.3 only; the independent Phase 1
completion gates `P1-REAL-TOOLCALL` and `P1-REAL-CANCEL` remain open.
