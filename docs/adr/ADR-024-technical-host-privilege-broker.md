# ADR-024 — Minimal Technical/host privilege broker

Status: Proposed / prepared; no privileged operations implemented  
Date: 2026-09-02

## Context

Most Assistant behavior belongs inside installable Odoo addons and should run with
the effective user's Odoo Environment. Some future P10 tasks—managed repository
acquisition, protected addon roots, OS packages, service restarts or database host
health—cannot always be performed correctly by an unprivileged Odoo process.

The retired general sidecar is not an acceptable solution. A generic shell, sudo,
Python, SQL or unrestricted Odoo method capability would enlarge authority beyond
the user and make effects unverifiable.

Product decisions are fixed:

- two human profiles only: User/non-technical and Technical;
- the broker is a technical boundary, not a third human group;
- addon-first architecture;
- arbitrary repositories may be candidates after bounded preflight;
- allowlists are optional trust/policy signals, not a universal repository block;
- approval depends on risk/policy/autonomy and explicit user intent;
- no free-form shell or method escape hatch.

## Proposed decision

When a deployment genuinely requires host privilege, use a minimal local broker
with a finite typed operation catalog. Everything that can be implemented safely in
Odoo remains in addons.

Candidate operations:

```text
repo.search
repo.inspect
repo.acquire
repo.promote
odoo.module.refresh
odoo.module.install
odoo.module.update
odoo.module.uninstall
host.service.status
host.service.restart
host.package.inspect
host.package.install
postgres.health
```

Each operation has a versioned schema, managed roots/services/packages, timeout,
output cap, effective actor/request binding, risk/policy classification, receipt and
recovery boundary. The broker runs under a separate OS identity and receives no
passwordless general root or command composition.

## Repository/module workflow

```text
resolve repo/branch/commit
 -> collect web/repository Evidence
 -> inspect manifest/README/license/dependencies
 -> bounded static/security/source scan
 -> assess compatibility and risk
 -> choose direct managed path or staging/extra approval from policy
 -> acquire/install/update
 -> verify registry/models/views/menus/capabilities/Evidence index
 -> issue receipt and usage guidance
```

An explicit user request to install already expresses intent. Low/known-risk actions
may execute directly in full-control when the effective user and policy allow it.
Elevated, uncertain or malicious findings invoke the configured risk response. The
model never grants permission itself.

## Security requirements

- Separate OS identity and managed roots.
- Remote plus selected commit binding.
- Allowed service units/package sources only.
- No shell string composition or arbitrary executable path.
- Nonces/request binding and replay protection.
- Bounded stdout/stderr converted to sanitized Evidence/receipts.
- Backup/rollback/recovery classification before irreversible work.
- Odoo ACL/company/policy binding retained across the broker request.
- Credentials stay in deployment-owned secret storage, never prompts/Evidence.

## Packaging

The customer experiences one Odoo AI Assistant product. Internal link/domain addons
may auto-install based on Odoo modules; the customer is not required to understand
the internal split. A broker, when a deployment enables it, is an optional host
adapter rather than the product runtime.

## Alternatives rejected

- Reintroducing the old operational sidecar.
- `shell(command)`, raw sudo, arbitrary Python or arbitrary SQL.
- Universal block of repositories not in a central allowlist.
- Running normal business operations as a shared technical user.
- Treating the broker as a new Developer/Operator/Admin-AI human role.

## Open deployment choices

These are adapters/configuration, not blockers for P8:

```text
managed addons root
systemd vs Docker vs Kubernetes
log source
single-db vs multi-db
backup mechanism
network/egress proxy
```

## Acceptance rule

ADR-024 remains proposed until P10 defines concrete deployment adapters, threat
model, request/receipt schemas, rollback behavior and real security gates. This P8
checkpoint does not expose or execute any host-privileged operation.
