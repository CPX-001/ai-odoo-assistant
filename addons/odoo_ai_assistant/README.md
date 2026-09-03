# Odoo AI Assistant addon

The supported product is an Odoo 18 Community addon with an embedded durable agent
runtime. The browser talks to Odoo; Codex App Server is an ephemeral provider
subprocess, not a product daemon.

## Product model

The customer installs one Odoo AI Assistant product. The addon is exposed as an Odoo
application for Knowledge, Diagnostics and Configuration while the chat remains
available from the systray.

There are exactly two public profile values:

```text
user
technical
```

Historical `business`/`developer` values are compatibility details only. The optional
P10 host broker is a machine execution boundary, not a third human role.

## Runtime flow

```text
OWL chat/context surface
 -> authenticated Odoo conversation + durable turn
 -> cron worker claims turn under effective user
 -> provider-neutral host decision loop
 -> effective Capabilities + Skills + JIT Context + Evidence
 -> bounded Evidence search/fetch when relevant
 -> Codex App Server adapter
 -> host validates calls/policy/effects
 -> execute with effective Environment and su=False
 -> verify, persist public activity and deliver final answer
```

Odoo owns identity, persistence, ACLs, record rules, companies, policy, approval,
execution and verification. The model proposes; it never grants itself authority.

## Capability framework

`runtime/capabilities/` contains the common extension contract:

- `CapabilityDefinition` — atomic executable schema/handler/risk/effect contract;
- `CapabilityProvider` — versioned installed-addon contribution boundary;
- `SkillDefinition` — trusted procedural guidance and selectors;
- `ContextProvider` — bounded just-in-time untrusted context;
- `EvidenceProvider` — bounded search/fetch with provenance/access/freshness;
- `EvidenceLedger` — bounded turn-scoped refs and selected excerpts.

Provider failures are isolated or fail closed according to provider optionality.
Deep JSON contracts are immutable after registration.

The framework exposes no arbitrary SQL, Python, shell, sudo or unrestricted Odoo
method invocation.

## Evidence and Knowledge

P8 provides runtime, installed-source/XML and configured-log Evidence with bounded
logical locators, access/freshness checks, fingerprints and citations.

P9 adds Odoo-native Knowledge sources/chunks/temporary attachments, company/private
record rules, deterministic bounded ingestion and PostgreSQL lexical FTS. Evidence
and documents are untrusted data and never grant capability authority.

## Autonomy and effects

Effects follow:

```text
discover -> inspect -> prepare -> preview -> policy
 -> approval when required -> durable barrier -> execute -> verify
 -> receipt / recovery
```

Full-control may suppress a redundant confirmation only when the effective user and
trusted policy already allow the operation. It cannot bypass ACLs, profile checks,
broker policy or hard safety stops. Ambiguous effects are not retried automatically.

## P10 Technical/host boundary

ADR-024 is accepted. The current addon defines Technical-only operations:

```text
odoo.module.inspect
postgres.health
odoo.config.inspect
odoo.config.patch
host.service.status
host.service.restart
```

The first two remain Odoo-local reads. Config/service operations call the optional
`host_broker/` adapter through a bounded AF_UNIX protocol.

Broker-backed effects retain PLAN/HOST semantics, preview, policy approval, exact
EffectPlan binding, verification and external recovery. A User/non-technical account
cannot discover them even under full autonomy.

Any transport or receipt loss after effect dispatch becomes
`host_effect_uncertain`; it is never treated as a safe-to-retry outage.

Not implemented:

```text
odoo.module.install/update/uninstall
repository/package promotion
generic command fallback
secret reveal
```

Odoo 18 immediate module maintenance is deliberately not invoked from the Assistant
cron worker. A lifecycle-safe maintenance adapter is required before the module-update
real gate can run.

## Controller and machine boundaries

All supported Assistant routes authenticate through Odoo. The retired `auth="none"`
inventory callback and addon machine-secret primitive are removed.

The optional P10 broker:

- runs no model;
- owns no chat/turn state;
- accepts no command or arbitrary path;
- verifies peer credentials;
- maps logical targets through deployment-owned policy;
- stores a durable effect request/receipt ledger;
- returns only bounded sanitized data.

## Source scope

Current source intelligence uses
`../../docs/CONTEXT_SOURCE_POLICY.md` and
`runtime/context_source_policy.json`. Historical `service/`, `installer`, old
migrations/tasks/evidence and secret-bearing roots are excluded by default.

## Validation state

```text
P0-P9 COMPLETE / ACCEPTED
P10 FIRST SLICE IMPLEMENTED
P10 FOCUSED + REAL VALIDATION NOT EXECUTED
P10-REAL-MODULE-UPDATE BLOCKED — ADAPTER MISSING
P10 NOT ACCEPTED
```

Prepared P10 tests:

```text
tests/unit/test_phase10_host_broker.py
tests/unit/test_phase10_host_broker_client.py
addons/odoo_ai_assistant/tests/test_phase10_host_operations.py
```

See:

```text
docs/research/EXECUTION_STATE.md
docs/research/P10_HOST_OPERATIONS_FIRST_SLICE.md
docs/research/P10_FOCUSED_VALIDATION_RUNBOOK.md
docs/adr/ADR-024-technical-host-privilege-broker.md
host_broker/README.md
```

Do not interpret code or committed tests as PASS evidence.

## Extension rule

Before adding another tool/action/retrieval system, extend the current framework. A
trusted installed addon should contribute a versioned provider rather than edit the
core catalog. Skills and Evidence may improve reasoning, but every executable
operation still resolves to a host-validated `CapabilityDefinition` and, for privileged
machine targets, the separately validated broker policy.
