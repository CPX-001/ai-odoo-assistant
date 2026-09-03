# P10 acceptance — bde508b

Date: 2026-09-03
Status: **PASS / COMPLETE / ACCEPTED**

## Accepted lineage

```text
bde508b737c132140e237cdfde31aee9b37eca5f
```

The tested checkout was `main`. Validation used Odoo 18 Community, Python 3.12.3,
PostgreSQL 16.15, systemd 255 and Codex CLI 0.144.2 on Ubuntu 24.04 under WSL2.
The real gates used only disposable database/config/module/service targets.

## Repairs made during validation

Three concrete failures were found and repaired:

1. focused lint and an incorrect immutable-list assertion were repaired at
   `bbfa78b`;
2. an effect retry refreshed `issued_at`/`expires_at`, while the broker replay hash
   incorrectly treated those transport-lifetime fields as effect identity. The hash
   now excludes only those volatile fields and still binds operation, phase, payload,
   capability and all durable plan fields (`bda2b19`);
3. module maintenance initially attempted a child-side UID drop. The hardened broker
   service can legitimately lose effective `CAP_SETUID`, so the final adapter asks
   systemd/PID 1 to launch a bounded transient unit under the policy-owned non-root
   UID/GID. No shell or model-selected executable/path was introduced (`bde508b`).

## Focused deterministic gates

Static compile and Ruff were executed over the changed P10 client, capability,
broker and focused-test surfaces.

```text
compileall                                      PASS
ruff                                            PASS — All checks passed
dependency-light broker/client                  PASS — 18 tests
Odoo TestPhase10HostOperations                  PASS — 5 methods, 0 failures/errors
example policy JSON                             PASS
reference systemd unit verification             PASS for the supplied unit
```

The Odoo gate used disposable database
`odoo_ai_p10_focus_20260903_cdx3`. Unrelated reStructuredText warnings from loaded
dependency metadata were non-failing.

## Disposable real environment

```text
database                 odoo_ai_p10_real_20260903_cdx2
broker caller            uid=109(odoo), gid=112(odoo), su=False in Odoo
broker socket            root:odoo 0660
policy                   root:root 0600
ledger/backups           root:root 0700
policy sha256             11cf2780f8203f1be8620affb0e1101dd3ca0d9c3aa96957f43c64f06985e5c8
config target            disposable fixture.conf
service target           disposable sleep fixture service
module target            disposable odoo_ai_p10_fixture
```

`broker.status` exposed only logical target ids and six finite operation names. It
did not expose paths, commands, policy contents or secrets. The hardened reference
shape used `NoNewPrivileges`, private tmp/home protections, kernel/control-group
protections, `ProtectSystem=strict`, AF_UNIX-only broker networking and exact writable
fixture/state directories.

## Named real gates

### P10-REAL-PROFILE-DENIAL — PASS

A real non-Technical internal user requested config patch and service restart under
the highest autonomy profile. The turn completed without any Technical capability or
EffectPlan and did not attempt sudo/shared-user fallback. The same run confirmed
effective Odoo execution with `su=False`.

### P10-REAL-CONFIG-PATCH — PASS

A real Technical Codex turn planned, executed and verified the logical config target.
Direct broker proof additionally confirmed:

- preview bound current/new values and the exact file fingerprint;
- one atomic write produced one private backup;
- replay after refreshed request timestamps returned the byte-equivalent stored
  receipt and created no second backup;
- replay after broker restart returned the same durable receipt;
- an external mutation between preview and execute returned
  `capability_plan_precondition_changed` and did not write.

### P10-REAL-SERVICE-OPERATION — PASS

A real Technical Codex turn restarted only the disposable logical service target and
verified `active/running`. Exact replay returned the original receipt without a
second restart. A response-loss proxy dropped the connection only after the real
broker durably received the execute result; the Odoo turn ended:

```json
{"error_code":"host_effect_uncertain","state":"recovery_required","write_barrier":true}
```

### P10-REAL-POSTGRES-DIAGNOSTIC — PASS

A real Technical turn used `postgres.health` and returned only the bounded fixed-query
health fields. The non-Technical profile could not discover it. No SQL argument or
mutation surface exists.

### P10-REAL-PRIVILEGE-BOUNDARY — PASS

Real broker attempts produced the expected fail-closed results:

```text
unknown config target                         broker_target_denied
absolute/path-like config target              broker_payload_invalid
secret-like config key                        broker_target_denied
injected service target                       broker_payload_invalid
wrong caller UID                              broker_peer_denied
wrong broker peer UID                         host_broker_peer_unverified
expired request                               broker_request_expired
execute without effect binding                broker_binding_invalid
same request id with changed payload          broker_request_replay_mismatch
unknown module target                         broker_target_denied
wrong module database binding                 broker_database_denied
```

Naming operations only in the non-Technical prompt did not create authority. The
socket was restored to `root:odoo 0660` after the caller-UID test.

### P10-REAL-MODULE-UPDATE — PASS

The disposable module began installed at `18.0.1.0.0` with observable value `v1`;
deployment source was advanced to `18.0.2.0.0`/`v2`. A real Technical Codex turn used
only `odoo.module.update`, crossed the durable write barrier and completed. The broker
launched the fixed Odoo CLI through a separate transient systemd unit as uid/gid
109/112 and then opened another fresh Odoo registry.

Observed after completion:

```json
{"database_version":"18.0.2.0.0","fixture_value":"v2","source_version":"18.0.2.0.0","state":"installed"}
```

Direct proof confirmed exact replay returned the same receipt without a second
update. A deliberately malformed disposable `18.0.3.0.0` source caused
`broker_module_update_failed` / `host_effect_uncertain`; replay returned that same
uncertain terminal result without executing again. Restoring the source left the
database and value at the verified v2 state.

### Broker absence/isolation — PASS

After stopping the broker/removing its live socket, broker-backed capabilities became
unavailable while `postgres.health` continued to work. The normal Odoo service was
restored active after the isolated worker runs.

## Scope honesty

The full repository, full addon, HOOT/browser and Product Behavior regressions were
not executed; they remain periodic validation debt. They were not required by the P10
runbook and no focused failure established a wider blast radius.

## Acceptance

All applicable P10 HARD gates passed on the accepted implementation lineage. The two
generic-command gates are **NOT APPLICABLE** because no generic command capability
ships. P10 is complete and the next roadmap cursor is Phase 11 advanced
imports/artifact workflows.
