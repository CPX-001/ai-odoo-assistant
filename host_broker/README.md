# Odoo AI Assistant host privilege broker

This directory contains the optional Phase 10 Linux host adapter accepted by
`docs/adr/ADR-024-technical-host-privilege-broker.md`.

It is **not** the Assistant runtime or the retired sidecar. Odoo still owns
conversations, turns, capability policy, approval and recovery. This process only
implements a finite deployment-owned privileged operation catalog.

## First supported operations

```text
broker.status
odoo.config.inspect
odoo.config.patch
host.service.status
host.service.restart
```

`odoo.module.inspect` and `postgres.health` are implemented in the addon without
privilege escalation. Effectful module install/update/uninstall is intentionally not
implemented here yet: Odoo 18 immediate module operations cannot safely run from the
Assistant cron worker and require a dedicated maintenance/restart reconciliation
adapter.

There is no shell, arbitrary executable, arbitrary filesystem path, Python, sudo
wrapper or arbitrary SQL endpoint.

## Deployment contract

Reference defaults:

```text
socket:   /run/odoo-ai-host-broker/broker.sock
policy:   /etc/odoo-ai-host-broker/policy.json
ledger:   /var/lib/odoo-ai-host-broker/execution.sqlite3
backups:  /var/lib/odoo-ai-host-broker/backups/
```

The broker validates the policy owner/mode, verifies the connecting process with
Linux `SO_PEERCRED`, and maps logical target ids to exact paths/systemd units from the
policy. The Odoo client verifies the broker peer UID as well.

The Odoo service user must be present in `allowed_peer_uids` and have filesystem
permission to connect to the socket. It does **not** need sudo/root.

Odoo-side deployment variables:

```text
ODOO_AI_ASSISTANT_HOST_BROKER_SOCKET=/run/odoo-ai-host-broker/broker.sock
ODOO_AI_ASSISTANT_HOST_BROKER_UID=0
```

The default expected broker UID is `0`.

## Installation and manual run

Install the deployment-owned package into a dedicated system Python/venv or an
administrator-managed site-packages location:

```bash
python3 -m pip install ./host_broker
```

For a disposable host:

```bash
python3 -m odoo_ai_host_broker \
  --policy /etc/odoo-ai-host-broker/policy.json \
  --socket /run/odoo-ai-host-broker/broker.sock \
  --state-db /var/lib/odoo-ai-host-broker/execution.sqlite3 \
  --backups-dir /var/lib/odoo-ai-host-broker/backups
```

The package is stdlib-only. Install/copy it as deployment code owned by the
administrator, not into a model-writable location.

## Policy

Start from `example-policy.json`. Replace the example UID and targets with values for
the deployment. Only keys in `allowed_keys` can be read/patched. Secret-like option names are also
denied by the broker in this first slice even if accidentally allowlisted; secret
configuration needs a later masked/reveal lifecycle. Only exact service targets in
`service_targets` can be inspected/restarted.

Do not add secret options such as `admin_passwd` to `allowed_keys` merely to make them
visible to the Assistant. The first slice is designed for non-secret operational
configuration.

## Replay and recovery

Effectful requests are inserted into the SQLite ledger as `running` before the
privileged barrier. Reusing the same request id/request hash returns the stored
terminal receipt instead of running again. A request left `running` after a broker
crash is reported as `uncertain` and is never blindly replayed.

Configuration patches keep a private backup in the broker state directory. Service
restart is classified `external_or_unknown`; a timeout/failure after the restart
barrier requires review rather than an automatic second restart.

## systemd

`systemd/odoo-ai-host-broker.service` is a reference unit, not a universal installer.
Its hardening must be reconciled with the exact config paths/services managed by the
deployment. If filesystem sandboxing is tightened further, explicitly grant only the
required targets.

## Tests

The dependency-light broker suite lives at
`tests/unit/test_phase10_host_broker.py` in the repository root after Phase 10
integration. Real acceptance additionally requires the P10 real gates documented in
`docs/research/P10_FOCUSED_VALIDATION_RUNBOOK.md`.
