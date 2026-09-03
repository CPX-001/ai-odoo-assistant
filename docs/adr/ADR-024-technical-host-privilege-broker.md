# ADR-024 — Minimal Technical/host privilege broker

Status: Accepted  
Proposed: 2026-09-02  
Accepted: 2026-09-03

## Context

Most Assistant behavior belongs inside installable Odoo addons and must continue to
run with the effective user's Odoo Environment. Some Phase 10 operations cross a real
host boundary: protected configuration files, service control, OS packages,
repository promotion or maintenance operations that cannot safely execute inside the
Assistant cron worker.

The retired general Assistant sidecar is not an acceptable solution. A generic shell,
passwordless sudo, Python, SQL or unrestricted Odoo method capability would enlarge
authority beyond the user, make effects difficult to bind to an approved plan and
make retries unsafe.

Product decisions remain fixed:

- the only human product profiles are User/non-technical and Technical;
- the broker is a machine privilege boundary, not a third human profile;
- normal business operations remain addon-first and use the effective Odoo user;
- arbitrary repositories may be candidates after bounded preflight; allowlists are
  policy/trust signals rather than a universal product block;
- approval depends on risk, configured policy/autonomy and explicit user intent;
- model text, retrieved content and capability arguments never create host authority;
- no free-form command or method escape hatch is accepted by this ADR.

## Decision

When a deployment genuinely requires host privilege, the product may use one minimal
local broker with a finite, versioned operation catalog. Everything that can be
implemented safely in Odoo remains in the addon.

The first supported deployment adapter is Linux with a local filesystem Unix-domain
socket. The broker is an optional adapter; it is not the Assistant runtime, does not
run the model, does not own conversations and does not replace the Odoo turn queue.

```text
Odoo user turn (su=False)
  -> CapabilityDefinition / EffectPlan
  -> host policy + approval when required
  -> bounded broker client
  -> AF_UNIX socket
  -> peer-credential check
  -> finite broker operation
  -> sanitized receipt
  -> capability verification / recovery state
```

The Odoo process itself receives no root shell and no passwordless general sudo.
The broker runs under a separate deployment-owned OS identity with only the privileges
required by its configured operations.

## Operation families

Logical operation names are stable contracts. Implementation support may be added by
version without exposing command composition.

```text
broker.status

odoo.config.inspect
odoo.config.patch

host.service.status
host.service.restart

odoo.module.inspect          # Odoo-local read when possible
odoo.module.install          # future maintenance adapter
odoo.module.update           # future maintenance adapter
odoo.module.uninstall        # future maintenance adapter

postgres.health              # Odoo-local fixed diagnostics when possible
postgres.activity            # optional bounded diagnostic adapter

repo.search                  # Evidence/web layer when possible
repo.inspect                 # Evidence/source layer when possible
repo.acquire                 # future broker version
repo.promote                 # future broker version

host.package.inspect         # future broker version
host.package.install         # future broker version
```

A capability is exposed only when both its Odoo-side requirements and the required
broker operation are available. Knowing an operation name never makes it executable.

### Important Odoo-module constraint

Odoo 18's immediate module install/update path commits and rebuilds the registry and
explicitly rejects module operations while a scheduled action holds `ir_cron`.
Assistant turns currently execute through native cron workers. Therefore Phase 10 must
**not** wrap `button_immediate_upgrade()` inside the current Assistant worker and call
that a safe module-update implementation.

A production `odoo.module.install/update/uninstall` operation requires a separate
maintenance adapter that can survive/reconcile the Odoo worker or service lifecycle,
return a durable broker receipt and verify the post-maintenance registry. Until that
adapter exists and its real gate passes, those effectful module capabilities remain
unavailable. `odoo.module.inspect` may remain an ordinary Technical read.

## Deployment-owned policy

The broker loads a local policy file controlled by deployment administrators. The
file must be owned by the broker identity (normally root for the reference systemd
adapter) and not writable by group/other.

Policy contains logical identifiers rather than model-supplied paths or commands:

```text
allowed_peer_uids
expected socket ownership/mode
config_targets:
  logical id -> absolute managed path + allowed option keys + size limit
service_targets:
  logical id -> exact systemd unit
timeouts/output limits
optional future maintenance targets
```

The model may choose only a logical target id and schema-valid operation arguments.
The broker resolves the actual path, service unit, executable and other privileged
resources from its own policy.

Allowlists in this policy are local execution constraints. They do not imply that
unknown repositories or modules are globally unsafe; candidate discovery/preflight is
a separate Evidence/risk process.

## Local authentication and identity binding

The reference adapter uses a filesystem `AF_UNIX` stream socket under a protected
runtime directory, for example:

```text
/run/odoo-ai-host-broker/broker.sock
```

The broker checks Linux peer credentials (`SO_PEERCRED`) and rejects UIDs not present
in its deployment policy. The Odoo client also verifies the broker peer UID configured
by deployment policy (root by default). Filesystem permissions are defense in depth,
not the sole authentication mechanism.

The Odoo user id carried in a request is an audit/binding field only. It never grants
OS privilege. Before the broker is called, the Odoo host must already have checked
Technical profile/group availability, capability schema, policy and any required
approval.

## Protocol v1

Transport is one bounded canonical JSON request and one bounded JSON response per
connection. No interactive shell/session exists.

### Request

```json
{
  "protocol_version": 1,
  "request_id": "req:v1:<stable-or-random-id>",
  "operation": "host.service.restart",
  "phase": "preview | execute | verify",
  "issued_at": 0,
  "expires_at": 0,
  "binding": {
    "turn_id": "...",
    "conversation_id": "... | null",
    "odoo_uid": 0,
    "database_fingerprint": "sha256:...",
    "capability": "host.service.restart",
    "step_id": "... | null",
    "args_sha256": "sha256:...",
    "binding_fingerprint": "sha256:... | null",
    "precondition_fingerprint": "sha256:... | null"
  },
  "payload": {}
}
```

The host generates `request_id`. For an effectful `execute`, it is stable for the
approved plan step/binding so a retry cannot silently become a second effect. Preview
and read requests may use non-replayable random ids.

The broker rejects:

- unknown protocol/operation/phase;
- expired or malformed requests;
- peer UID mismatch;
- unknown logical targets;
- payload fields outside the operation schema;
- execution whose expected precondition no longer matches;
- reused `request_id` with a different canonical request hash.

### Receipt

```json
{
  "protocol_version": 1,
  "request_id": "...",
  "receipt_id": "receipt:v1:...",
  "operation": "host.service.restart",
  "phase": "execute",
  "status": "ok | denied | stale | error | uncertain",
  "effect_state": "none | applied | unknown",
  "precondition_fingerprint": "sha256:... | null",
  "postcondition_fingerprint": "sha256:... | null",
  "summary": {},
  "recovery": {
    "classification": "none | backup_available | external_or_unknown",
    "token": "opaque-or-null"
  },
  "error_code": "sanitized_code | null",
  "started_at": 0,
  "completed_at": 0
}
```

Raw stdout/stderr, environment variables, credentials, file contents containing
secrets and arbitrary exception strings are never returned as product receipts.
Operation-specific parsers emit only bounded structured fields.

## Replay, idempotency and uncertain effects

The reference broker persists an execution ledger in deployment-owned state (SQLite
is sufficient for the local adapter). Before an effectful operation crosses its host
barrier it stores:

```text
request_id
canonical request hash
operation
state = running
started_at
```

On completion it atomically stores the terminal sanitized receipt.

Rules:

1. same `request_id` + same request hash + terminal receipt -> return the existing
   receipt without executing again;
2. same `request_id` + different request hash -> deny as replay/binding mismatch;
3. request found in `running` after broker/host interruption -> return `uncertain` and
   do not execute again automatically;
4. the Odoo effect runtime treats `uncertain` as recovery-required evidence, never as
   proof that no effect occurred.

This broker ledger complements the Odoo EffectJournal; it does not replace it.

## Concrete first-slice operations

### `odoo.config.inspect` / `odoo.config.patch`

- Input contains a logical config target id and one configured option key.
- Path is resolved only from broker policy.
- File size, value size and syntax are bounded.
- `patch` preview returns current/new value plus a file fingerprint.
- Execute requires the exact preview fingerprint.
- Write uses a same-filesystem temporary file, fsync and atomic replace while
  preserving managed ownership/mode.
- A root/private backup is stored in broker state before replacement.
- Verify re-reads the configured key and fingerprint.
- Recovery classification is `backup_available`; rollback is an explicit reviewed
  operation, not an automatic blind retry.

### `host.service.status` / `host.service.restart`

- Input contains only a logical service target id.
- Broker policy maps it to exactly one systemd unit.
- Commands are fixed argv executed with `shell=False`; no arbitrary executable path,
  unit suffix or environment is accepted from the model.
- Status returns only parsed bounded fields such as ActiveState/SubState and main
  exit status.
- Restart requires a preview/status fingerprint and verifies post-restart health.
- Timeout/transport interruption after the restart barrier is `effect_state=unknown`.
- Recovery classification is `external_or_unknown`; the broker never claims a
  rollback it cannot guarantee.

### `postgres.health`

The first implementation should stay inside Odoo when fixed read-only SQL available
to the Odoo database role is sufficient. It may expose bounded counts/version/size and
wait-state facts, never arbitrary SQL, query text or database-admin mutation.
Privilege escalation is not introduced merely to call this diagnostic.

## Threat model

The boundary is designed against at least:

| Threat | Required response |
| --- | --- |
| Prompt/retrieved text asks for shell/root | No matching operation; reject |
| Model invents `/etc/...` path or service name | Payload schema/logical-target resolution rejects it |
| Business user names a Technical capability | Odoo registry/group guard keeps it unavailable |
| Full autonomy tries to exceed profile/ACL | Autonomy cannot create availability/authority |
| Malicious local process connects to socket | Filesystem mode + `SO_PEERCRED` UID policy |
| Fake broker socket/server | Odoo client verifies configured broker peer UID |
| Request replay | Stable id + canonical hash ledger |
| Crash during external effect | Persist `running`; return uncertain; no blind replay |
| Config changes between preview and execute | Fingerprint mismatch -> stale/deny |
| Command injection through target/value | No shell; target comes from policy; values are data with strict bounds |
| Host output contains secrets | Parse/redact; bounded structured receipt only |
| Broker policy is modified by untrusted user | Secure owner/mode validation; fail closed |

The broker does not attempt to defend a host where the attacker already controls the
broker OS identity or root. That is outside the Assistant trust boundary.

## Recovery matrix

| Operation family | Failure before barrier | Failure after barrier | Automatic replay |
| --- | --- | --- | --- |
| inspect/status/health | no effect | n/a | safe read only |
| config patch | no effect | backup + verify/review | no |
| service restart | no effect | external/unknown + health review | no |
| module maintenance | no effect | durable maintenance receipt required | no |
| repository/package promotion | no effect | operation-specific receipt/rollback required | no |

## Packaging and systemd reference

The customer still experiences one Odoo AI Assistant product. The broker is enabled
only on deployments that need host operations.

The reference systemd deployment should use a dedicated service identity/runtime
state, a protected Unix socket and hardening compatible with the exact managed
resources. Recommended controls include a restrictive umask, private temporary space,
no writable home, explicit filesystem access and no ambient general-purpose shell
surface. Hardening must be validated against the deployment instead of copied blindly
when it would block the configured operation.

Container/Kubernetes deployments may provide an equivalent adapter, but must preserve
the same logical-target/request/receipt/replay contract. The protocol contract is more
important than systemd itself.

## Approval and product profiles

Host-effect capabilities use the existing `CapabilityDefinition` risk/effect/policy
model. `CapabilityEffect.HOST`/`CapabilityRisk.HOST` maps to the protected risk band.
`approval=POLICY` therefore allows a deployment's full-control policy to suppress a
redundant confirmation only when the Technical capability is already available and
policy explicitly permits protected auto-execution.

This does not expand either Odoo or broker authority. User/non-technical profile
cannot access Technical host operations even in full autonomy.

## Command fallback

P10.3's generic Developer command fallback is **not accepted or shipped** by this ADR.
If a later measured use case cannot be expressed with high-level typed operations, a
separate ADR and the conditional command-sandbox/approval real gates are required
before any such capability is introduced.

## Alternatives rejected

- Reintroducing the old operational Assistant sidecar.
- `shell(command)`, raw sudo, arbitrary Python or arbitrary SQL.
- Universal block of repositories not in a central allowlist.
- Running normal business operations as a shared technical user.
- Treating the broker as a Developer/Operator/Admin-AI human role.
- Calling Odoo immediate module upgrade from the current Assistant cron worker despite
  Odoo's scheduled-action/registry constraints.
- Treating transport success as effect verification.

## Acceptance and implementation gates

This ADR is accepted as the mandatory P10 privilege boundary. Acceptance of the ADR
does **not** claim that the broker or any P10 real operation already passes.

P10 implementation must add deterministic coverage for profile denial, broker
availability, peer policy, target/path escape, stale preconditions, replay/uncertain
state, sanitized receipts and operation verification.

Phase 10 cannot be accepted until the applicable real product gates execute and pass:

```text
P10-REAL-PROFILE-DENIAL
P10-REAL-MODULE-UPDATE
P10-REAL-CONFIG-PATCH
P10-REAL-SERVICE-OPERATION
P10-REAL-POSTGRES-DIAGNOSTIC
P10-REAL-PRIVILEGE-BOUNDARY
```

If a generic command fallback is ever promoted, these become additionally mandatory:

```text
P10-REAL-COMMAND-SANDBOX
P10-REAL-COMMAND-APPROVAL
```
