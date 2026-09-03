# P10 typed host-operations first slice

State: `IMPLEMENTED / VALIDATED / ACCEPTED`
Date: 2026-09-03  
ADR: `docs/adr/ADR-024-technical-host-privilege-broker.md`

## 1. Scope

This checkpoint implements the first bounded Phase-10 Technical/host boundary without
turning the Odoo worker into root and without reintroducing the retired Assistant
sidecar.

The slice reuses the accepted capability and effect runtime:

```text
Technical user + effective Odoo env (su=False)
 -> effective CapabilityRegistry
 -> typed CapabilityDefinition
 -> preview / policy / approval when required
 -> durable EffectPlan binding + write barrier
 -> optional AF_UNIX privilege broker
 -> finite deployment-owned operation
 -> sanitized receipt
 -> verification / recovery state
```

`CapabilityDefinition`, the registry, policy and EffectPlan remain authoritative.
The broker is an optional execution adapter. It does not run the model, own
conversations or replace the Odoo queue.

## 2. Implemented capabilities

### Odoo-local Technical reads

```text
odoo.module.inspect
postgres.health
```

`odoo.module.inspect` reads one named module from the current Odoo registry/database
and returns bounded state, version, license and dependency metadata. It does not call
module install/update methods.

`postgres.health` executes only fixed host-owned read SQL for the current database and
returns server version, database size and bounded backend/wait counts. It accepts no
query text and exposes no arbitrary SQL surface.

Both capabilities require `base.group_system` and execute through the effective
non-sudo Odoo Environment.

### Broker-backed reads and effects

```text
odoo.config.inspect
odoo.config.patch
host.service.status
host.service.restart
odoo.module.update
```

The broker-backed definitions are available only to `base.group_system` users and
only while the configured Unix socket exists. The final request still rechecks the
broker peer UID, wire contract and broker-owned policy.

`odoo.config.patch` and `host.service.restart` are PLAN capabilities with:

```text
risk = host
effect = host
approval = policy
recovery_mode = external
journal_classification = external_or_unknown
preview + execute + verify
```

They therefore use the existing protected-risk policy and cannot become executable
because the model merely knows their names.

`odoo.module.update` uses that same HOST/PLAN/policy lifecycle. Its input is only a
logical maintenance target. Broker policy fixes the module, database, Python/Odoo
executables, config, addons paths, non-root OS identity and timeout. It launches a
separate transient systemd unit outside the Assistant cron worker and verifies the
result from a second fresh Odoo registry before returning success.

## 3. Optional local broker package

The root `host_broker/` package is a stdlib-only Linux adapter with:

- one bounded canonical JSON request and receipt per AF_UNIX connection;
- Linux `SO_PEERCRED` verification in both directions;
- a root/deployment-owned policy mapping logical target ids to exact paths or systemd
  units;
- strict request lifetime, size, schema, operation, target, fingerprint and binding
  checks;
- fixed-argv `systemctl` calls with `shell=False`;
- fixed-argv `systemd-run` module maintenance under a policy-owned non-root UID/GID;
- atomic config replacement, fsync and private backup;
- bounded parsed service/config results rather than raw stdout/stderr;
- a durable SQLite execution ledger for effect request replay and uncertainty;
- a hardened reference systemd unit and example policy.

There is no generic shell, command string, arbitrary executable, arbitrary path,
Python, sudo wrapper, arbitrary SQL or unrestricted Odoo-method operation.

## 4. Durable request and receipt binding

An effectful broker request is bound to the exact durable EffectPlan step using:

```text
turn id
conversation id
Odoo uid
hashed database identity
capability / operation
step id
canonical args hash
plan binding fingerprint
preview precondition fingerprint
```

The request id is stable for that exact approved effect. Before crossing the broker
barrier, the broker ledger records the request as `running`. A terminal replay returns
the stored receipt; a hash mismatch is denied; a still-running request is uncertain
and is never blindly executed again.

The Odoo-side client resolves the binding from the plan persisted at the write barrier
when it is not already present in host metadata. This prevents model text or an
uncommitted proposal from inventing host authority.

## 5. Transport-certainty hardening

The initial implementation treated a socket loss as `host_broker_unavailable` even
when it happened after an effectful request started sending. That could incorrectly
suggest a safe retry although the broker may already have applied the host effect.

The client now tracks the dispatch boundary. For effectful calls:

- peer/connect failure before sending remains a no-dispatch connectivity/identity
  failure;
- any transport, framing, decoding or receipt-validation failure after dispatch is
  normalized to `host_effect_uncertain`;
- an authoritative broker `stale`, `denied`, `error` or `uncertain` receipt keeps its
  explicit semantics;
- reads retain ordinary unavailable/invalid-response behavior because they have no
  side effect.

Dedicated dependency-light coverage exercises post-dispatch loss, malformed receipts,
read-only loss and peer rejection before dispatch.

## 6. Deployment policy and first-slice limits

The deployment policy, not the model, selects:

```text
allowed peer UIDs
socket group
exact config target paths
allowed non-secret config keys
exact systemd service units
exact module/database/Odoo runtime targets and maintenance UID/GID
operation timeouts
```

Secret-like config option names are denied even if accidentally listed. A later
masked/copy/reveal secret lifecycle is required before secret inspection can be a
product feature.

The supplied systemd unit is a reference. Its `ReadWritePaths` must be reconciled with
the actual directory semantics required by atomic replacement; deployments must not
broaden access to a filesystem root merely to make the broker work.

A service target should first be a disposable/auxiliary fixture. Restarting the Odoo
service that owns the active Assistant worker requires lifecycle/reconciliation proof
and must not be inferred from the generic service capability.

## 7. Explicitly not implemented

P10 still does not implement:

```text
odoo.module.install/uninstall
repository acquisition or promotion
host package installation
postgres arbitrary activity/query inspection
config rollback capability
generic Developer command fallback
```

Odoo 18 module updates therefore do not call `button_immediate_upgrade()` inside the
Assistant `ir.cron` worker. The implemented maintenance adapter runs the fixed Odoo
CLI operation separately, persists the broker receipt exactly once and inspects a
fresh registry. Install/uninstall, repository acquisition and arbitrary module names
remain outside the surface.

## 8. Failure and recovery semantics

| Condition | Required result |
| --- | --- |
| User lacks Technical group | Capability unavailable; autonomy cannot override |
| Broker socket absent | Broker-backed capabilities unavailable |
| Wrong broker or caller UID | Denied before effect dispatch |
| Unknown logical target/key/unit | Denied by broker policy |
| Config/service state changed after preview | `stale`; no effect |
| Same request id and same terminal request | Return stored receipt; do not re-execute |
| Same request id with changed payload/binding | Deny replay mismatch |
| Broker ledger says request still running | `host_effect_uncertain`; no blind replay |
| Transport/receipt lost after effect dispatch | `host_effect_uncertain`; recovery review |
| Config patch verified | Receipt + postcondition fingerprint + private backup token |
| Service restart cannot be proven healthy | external/unknown recovery state |
| Module target/database differs from policy | Denied before maintenance launch |
| Module update fails or times out | Durable uncertain receipt; no blind replay |
| Module update succeeds | Fresh-registry source/database versions must match |

## 9. Executed validation surface

Dependency-light tests:

```text
tests/unit/test_phase10_host_broker.py
tests/unit/test_phase10_host_broker_client.py
```

Odoo-focused tests:

```text
addons/odoo_ai_assistant/tests/test_phase10_host_operations.py
```

These files were executed in the applicable interpreter/Odoo environment. The gate
contract remains in `P10_FOCUSED_VALIDATION_RUNBOOK.md`; immutable results are in the
acceptance evidence linked below.

## 10. Acceptance and next action

All applicable focused and real gates passed on the lineage recorded in
`evidence/phase10/2026-09-03/P10-ACCEPTANCE-bde508b.md`. P10 is accepted. The next
roadmap action is to design the first coherent Phase-11 `DataImportSession` slice.
